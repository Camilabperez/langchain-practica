import json
import os
from azure.devops.connection import Connection
from azure.devops.v7_0.search.models import WikiSearchRequest
from msrest.authentication import BasicAuthentication
from langchain.tools import StructuredTool
from pydantic import BaseModel, Field
from typing import List, Dict, Any
from urllib.parse import unquote
import streamlit as st

class EdgeWikiClient:
    """Cliente para interactuar con Azure DevOps Wiki usando las librerías oficiales"""
    
    def __init__(self, org: str = None, project: str = None, pat: str = None):
        self.org = org or os.getenv('ORG', 'Labs-DevOps')
        self.project = project or os.getenv('PROJECT', 'Wiki productos de IBM')
        self.pat = pat or os.getenv('AZDO_PAT')
        
        if not self.pat:
            raise ValueError("❌ PAT no configurado. Configura AZDO_PAT en tu .env")
        
        self.connection = self._get_connection()
        
    def _get_connection(self) -> Connection:
        """Establece conexión con Azure DevOps"""
        organization_url = f'https://dev.azure.com/{self.org}'
        credentials = BasicAuthentication('', self.pat)
        connection = Connection(base_url=organization_url, creds=credentials)
        return connection
    
    def _get_wiki_url(self, project_id: str, wiki_id: str, path: str) -> str:
        """Construye la URL para la página del wiki"""
        correct_path = path.replace("-", "%20").replace(".md", "")
        return f'https://dev.azure.com/{self.org}/{project_id}/_wiki/wikis/{wiki_id}/?pagePath={correct_path}'
    
    def search_wiki(self, query: str) -> List[Dict[str, Any]]:
        """Busca en el wiki usando la API de search"""
        try:
            search_client = self.connection.clients.get_search_client()
            
            search_request = WikiSearchRequest(search_text=query, top=500)
            result = search_client.fetch_wiki_search_results(
                request=search_request, 
                project=self.project
            )
        
            return [{
                'file_name': wiki.file_name,
                'path': wiki.path,
                'wiki_id': wiki.wiki.id,
                'project_id': wiki.project.id,
                'url': self._get_wiki_url(wiki.project.id, wiki.wiki.id, wiki.path),
            } for wiki in result.results]
            
        except Exception as e:
            raise Exception(f"Error searching wiki: {str(e)}")
    
    def get_wiki_by_path(self, path: str, wiki_id: str) -> Dict[str, Any]:
        """Obtiene el contenido de una página del wiki por su path"""
        try:
            wiki_client = self.connection.clients.get_wiki_client()
            
            # Limpiar el path como en edge_wiki.py
            correct_path = path.replace("-", " ")
            if correct_path.endswith('.md'):
                correct_path = correct_path[:-3]
            
            correct_path = unquote(correct_path)
            result = wiki_client.get_page(
                project=self.project, 
                wiki_identifier=wiki_id, 
                path=correct_path, 
                include_content=True
            )
            
            return {
                'path': result.page.path,
                'content': result.page.content,
                'url': self._get_wiki_url(self.project, wiki_id, path)
            }
            
        except Exception as e:
            raise Exception(f"Error getting wiki page: {str(e)}")
    
    def list_wikis(self) -> List[Dict[str, Any]]:
        """Lista todos los wikis disponibles en el proyecto"""
        try:
            wiki_client = self.connection.clients.get_wiki_client()
            wikis = wiki_client.get_all_wikis(project=self.project)
            
            return [{
                'id': wiki.id,
                'name': wiki.name,
                'type': wiki.type,
                'url': wiki.url if hasattr(wiki, 'url') else None
            } for wiki in wikis]
            
        except Exception as e:
            raise Exception(f"Error listing wikis: {str(e)}")

# Modelos Pydantic para las herramientas
class WikiSearchInput(BaseModel):
    query: str = Field(description="Término de búsqueda para el wiki")
    wiki_id: str = Field(description="ID del wiki", default=None)

class WikiPageInput(BaseModel):
    path: str = Field(description="Path de la página del wiki")
    wiki_id: str = Field(description="ID del wiki", default=None)

class EmptyInput(BaseModel):
    pass

def create_edge_wiki_tools(org: str = None, project: str = None, pat: str = None) -> List[StructuredTool]:
    """Crea las herramientas de LangChain para Edge Wiki"""
    
    try:
        client = EdgeWikiClient(org=org, project=project, pat=pat)
        print(f"✅ EdgeWikiClient inicializado para {client.org}/{client.project}")
    except Exception as e:
        print(f"❌ Error inicializando EdgeWikiClient: {e}")
        return []
    
    def search_wiki_tool(query: str, wiki_id: str = None) -> str:
        """Busca contenido en el wiki, opcionalmente filtrando por wiki_id"""
        actual_query_text = query 
        actual_wiki_id = wiki_id 

        # Lógica para intentar parsear el input si viene como un JSON string
        if isinstance(query, str) and query.strip().startswith('{') and query.strip().endswith('}'):
            try:
                parsed_input = json.loads(query)
                if 'query' in parsed_input:
                    actual_query_text = parsed_input['query']
                if 'wiki_id' in parsed_input:
                    actual_wiki_id = parsed_input['wiki_id']
                print(f"DEBUG: Input parseado: query='{actual_query_text}', wiki_id='{actual_wiki_id}'") # Nuevo print para depurar
            except json.JSONDecodeError:
                pass 

        try:
            results = client.search_wiki(actual_query_text)
            
            if actual_wiki_id: 
                results = [r for r in results if r['wiki_id'] == actual_wiki_id]
            
            if not results:
                return json.dumps({
                    "results": [],
                    "message": f"No se encontraron resultados para el término '{actual_query_text}' en el wiki '{actual_wiki_id or 'Sin especificar'}'."
                }, ensure_ascii=False)
            
            formatted_results = []
            for result in results[:10]:
                formatted_results.append({
                    'file_name': result['file_name'],
                    'path': result['path'],
                    'wiki_id': result['wiki_id'],
                    'url': result['url']
                })
            return json.dumps(formatted_results, indent=2, ensure_ascii=False)
        except Exception as e:
            return f"Error buscando en wiki: {str(e)}"
    
    def get_wiki_page_tool(path: str, wiki_id: str = None) -> str:
        """Obtiene el contenido completo de una página del wiki"""
        actual_path = path
        actual_wiki_id = wiki_id

        # Lógica para intentar parsear el input si viene como un JSON string
        if isinstance(path, str) and path.strip().startswith('{') and path.strip().endswith('}'):
            try:
                parsed_input = json.loads(path)
                if 'path' in parsed_input:
                    actual_path = parsed_input['path']
                if 'wiki_id' in parsed_input:
                    actual_wiki_id = parsed_input['wiki_id']
            except json.JSONDecodeError:
                pass

        # Asegúrate de que actual_wiki_id no sea None en este punto, ya que es requerido
        if actual_path is None or actual_wiki_id is None:
            return json.dumps({
                "error": "path and wiki_id are required for edge_wiki_get_page",
                "received_path_arg": path, # Usamos los argumentos originales para depurar
                "received_wiki_id_arg": wiki_id,
                "processed_path": actual_path, # Y los procesados
                "processed_wiki_id": actual_wiki_id
            }, ensure_ascii=False)

        try:
            result = client.get_wiki_by_path(actual_path, actual_wiki_id)
            return json.dumps(result, indent=2, ensure_ascii=False)
        except Exception as e:
            return f"Error obteniendo página del wiki: {str(e)}"
    
    def list_wikis_tool() -> str:
        """Lista todos los wikis disponibles"""
        try:
            wikis = client.list_wikis()
            return json.dumps(wikis, indent=2, ensure_ascii=False)
            
        except Exception as e:
            return f"Error listando wikis: {str(e)}"
    
    # Crear herramientas estructuradas
    tools = [
        StructuredTool.from_function(
            func=search_wiki_tool,
            name="edge_wiki_search",
            description="Busca contenido en Azure DevOps Wiki. Útil para encontrar páginas relacionadas con un tema específico.",
            args_schema=WikiSearchInput
    ),
        StructuredTool.from_function(
            func=get_wiki_page_tool,
            name="edge_wiki_get_page",
            description="Obtiene el contenido completo de una página del wiki usando su path y wiki_id obtenidos de la búsqueda.",
            args_schema=WikiPageInput
        ),
        StructuredTool.from_function(
            func=list_wikis_tool,
            name="edge_wiki_list_wikis",
            description="Lista todos los wikis disponibles en el proyecto de Azure DevOps.",
            args_schema=EmptyInput
        )
    ]
    
    return tools

def test_edge_wiki_connection(org: str = None, project: str = None, pat: str = None) -> str:
    """Función para probar la conexión con Azure DevOps Wiki"""
    try:
        client = EdgeWikiClient(org=org, project=project, pat=pat)
        
        # Test 1: Listar wikis
        wikis = client.list_wikis()
        
        results = []
        results.append(f"✅ Conexión exitosa a {client.org}/{client.project}")
        results.append(f"📚 Wikis encontrados: {len(wikis)}")
        
        for wiki in wikis:
            results.append(f"  - {wiki['name']} (ID: {wiki['id']}, Tipo: {wiki['type']})")
        
        # Test 2: Buscar algo simple
        if wikis:
            wiki_id = wikis[0]['id']
            search_results = client.search_wiki("test")
            results.append(f"🔍 Resultados de búsqueda 'test': {len(search_results)}")
            
            # Test 3: Obtener una página si existe
            if search_results:
                try:
                    first_result = search_results[0]
                    page_content = client.get_wiki_by_path(first_result['path'], first_result['wiki_id'])
                    results.append(f"📄 Página obtenida: {first_result['file_name']}")
                    results.append(f"📝 Contenido: {len(page_content['content'])} caracteres")
                except Exception as e:
                    results.append(f"⚠️ Error obteniendo página: {str(e)}")
        
        return "\n".join(results)
        
    except Exception as e:
        return f"❌ Error en la conexión: {str(e)}"

# Función para integrar con Streamlit
def add_edge_wiki_to_sidebar():
    """Agrega controles de Edge Wiki al sidebar de Streamlit"""
    st.sidebar.markdown("### Edge Wiki")
    
    if st.sidebar.button("🔍 Probar Edge Wiki"):
        with st.sidebar:
            with st.spinner("Probando conexión..."):
                result = test_edge_wiki_connection()
                st.text_area("Resultado:", result, height=200)
    
    if st.sidebar.button("📚 Listar Wikis"):
        try:
            client = EdgeWikiClient()
            wikis = client.list_wikis()
            st.sidebar.success(f"✅ {len(wikis)} wikis encontrados")
            for wiki in wikis:
                st.sidebar.write(f"- **{wiki['name']}** (ID: {wiki['id']})")
        except Exception as e:
            st.sidebar.error(f"❌ Error: {e}")

if __name__ == "__main__":
    # Test básico
    print("🧪 Probando EdgeWikiClient...")
    result = test_edge_wiki_connection()
    print(result)
