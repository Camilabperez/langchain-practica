
from langchain.tools import tool
@tool
def search_wikipedia(query):
    """Useful for when you need to know information about a topic. Searches Wikipedia and returns the summary of the first result."""
    from wikipedia import summary

    try:
        # Limit to two sentences for brevity
        return summary(query, sentences=2)
    except:
        return "I couldn't find any information on that."
