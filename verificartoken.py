#!/usr/bin/env python3
"""
Script para verificar que el token PAT de Azure DevOps funcione correctamente
"""
import os
import requests
import base64
import json
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

def verify_pat_token():
    """Verifica que el token PAT funcione correctamente"""
    
    # Obtener variables de entorno
    org_url = os.getenv('AZDO_ORG_URL')
    pat_token = os.getenv('AZDO_PAT')
    project = os.getenv('AZDO_DEFAULT_PROJECT', 'Prueba-MCP')
    
    if not org_url or not pat_token:
        print("❌ Error: AZDO_ORG_URL y AZDO_PAT deben estar configurados")
        return False
    
    print(f"🔍 Verificando token PAT para: {org_url}")
    print(f"📝 Proyecto: {project}")
    print(f"🔑 Token length: {len(pat_token)} caracteres")
    
    # Crear headers de autenticación
    auth_string = f":{pat_token}"
    encoded_auth = base64.b64encode(auth_string.encode()).decode()
    
    headers = {
        'Authorization': f'Basic {encoded_auth}',
        'Content-Type': 'application/json'
    }
    
    # Test 1: Verificar acceso a la organización
    print("\n🧪 Test 1: Acceso a la organización")
    try:
        response = requests.get(f"{org_url}/_apis/projects", headers=headers)
        if response.status_code == 200:
            projects = response.json()
            print(f"✅ Acceso exitoso - {len(projects['value'])} proyectos encontrados")
            
            # Mostrar proyectos
            for proj in projects['value']:
                print(f"   - {proj['name']} (ID: {proj['id']})")
        else:
            print(f"❌ Error accediendo a proyectos: {response.status_code}")
            print(f"   Respuesta: {response.text}")
            return False
    except Exception as e:
        print(f"❌ Error de conexión: {e}")
        return False
    
    # Test 2: Verificar acceso al proyecto específico
    print(f"\n🧪 Test 2: Acceso al proyecto '{project}'")
    try:
        response = requests.get(f"{org_url}/_apis/projects/{project}", headers=headers)
        if response.status_code == 200:
            project_info = response.json()
            print(f"✅ Proyecto encontrado: {project_info['name']}")
            print(f"   Estado: {project_info['state']}")
            print(f"   ID: {project_info['id']}")
        else:
            print(f"❌ Error accediendo al proyecto: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ Error accediendo al proyecto: {e}")
        return False
    
    # Test 3: Verificar acceso a wikis
    print(f"\n🧪 Test 3: Acceso a wikis del proyecto")
    try:
        response = requests.get(f"{org_url}/{project}/_apis/wiki/wikis", headers=headers)
        if response.status_code == 200:
            wikis = response.json()
            print(f"✅ Wikis encontradas: {len(wikis['value'])}")
            
            for wiki in wikis['value']:
                print(f"   - {wiki['name']} (ID: {wiki['id']})")
                print(f"     Tipo: {wiki['type']}")
                print(f"     URL: {wiki['remoteUrl']}")
        else:
            print(f"❌ Error accediendo a wikis: {response.status_code}")
            print(f"   Respuesta: {response.text}")
            return False
    except Exception as e:
        print(f"❌ Error accediendo a wikis: {e}")
        return False
    
    # Test 4: Verificar permisos del token
    print(f"\n🧪 Test 4: Verificar permisos del token")
    try:
        # Intentar acceder a una página de wiki específica
        response = requests.get(f"{org_url}/{project}/_apis/wiki/wikis", headers=headers)
        if response.status_code == 200:
            wikis = response.json()
            if wikis['value']:
                wiki_id = wikis['value'][0]['id']
                
                # Intentar listar páginas
                pages_response = requests.get(
                    f"{org_url}/{project}/_apis/wiki/wikis/{wiki_id}/pages",
                    headers=headers
                )
                
                if pages_response.status_code == 200:
                    print("✅ Permisos de lectura de wiki: OK")
                else:
                    print(f"⚠️  Permisos de lectura limitados: {pages_response.status_code}")
            else:
                print("⚠️  No hay wikis disponibles para probar permisos")
        
    except Exception as e:
        print(f"❌ Error verificando permisos: {e}")
    
    print(f"\n🎉 Token PAT verificado exitosamente!")
    return True

def show_token_scopes():
    """Muestra información sobre los scopes necesarios para el token"""
    print("\n📋 Scopes necesarios para el token PAT:")
    print("   🔸 Wiki (Read): vso.wiki - Para leer páginas de wiki")
    print("   🔸 Wiki (Write): vso.wiki_write - Para crear/editar páginas")
    print("   🔸 Project (Read): vso.project - Acceso básico al proyecto")
    print("   🔸 Code (Read): vso.code - Si la wiki está en un repositorio")
    
    print("\n🔧 Para crear un nuevo token:")
    print("   1. Ve a https://dev.azure.com/camilabperez/_usersSettings/tokens")
    print("   2. Crea un nuevo token con los scopes mencionados")
    print("   3. Actualiza la variable AZDO_PAT en tu archivo .env")

if __name__ == "__main__":
    print("🚀 Verificador de Token PAT de Azure DevOps")
    print("=" * 50)
    
    if verify_pat_token():
        print("\n✅ El token PAT está funcionando correctamente")
        print("   El problema está en la configuración del servidor MCP")
        print("   Recomendación: Usar 'az login' como solución temporal")
    else:
        print("\n❌ Hay problemas con el token PAT")
        show_token_scopes()