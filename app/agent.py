import re
import httpx
import json
from pathlib import Path

class Agent:
    def __init__(self, system=""):
        self.system = system
        self.messages = []
        # Ollama API endpoint - default local installation
        self.api_url = "http://localhost:11434/api/chat"
        # Can be configured to any Ollama model
        #self.model = "llama3:latest"
        #self.model = "gpt-oss:latest"
        #self.model = "phi4-mini:latest"
        self.model = "gemma4:latest"
        if self.system:
            self.messages.append({"role": "system", "content": system})
    
    def __call__(self, message):
        self.messages.append({"role": "user", "content": message})
        result = self.execute()
        self.messages.append({"role": "assistant", "content": result})
        return result
    
    def execute(self):
        payload = {
            "model": self.model,
            "messages": self.messages,
            "stream": False,
            # Ollama's options parameter to set context window size
            "options": {
                "num_ctx": 32768  # Adjust value (e.g., 8192, 16384, 32768)
            }
        }
        
        try:
            response = httpx.post(
                self.api_url, 
                json=payload,
                timeout=60.0  # 60 second timeout
            )
            if response.status_code == 200:
                return response.json()["message"]["content"]
            else:
                raise Exception(f"Ollama API error: {response.text}")
        except httpx.ReadTimeout:
            raise Exception("Connection to Ollama timed out. Make sure Ollama is running (ollama serve) and the model is downloaded.")
        except httpx.ConnectError:
            raise Exception("Could not connect to Ollama. Make sure the Ollama server is running (ollama serve).")

# Define name of prompt file
prompt_filename = "system-prompt.txt"
# Construct path and read file directly
system_prompt = (Path(__file__).parent.parent / "prompts" / prompt_filename).read_text(encoding='utf-8').strip()

action_re = re.compile(r'^Action: (\w+): (.*)$')

def stream_query(question, max_turns=5, max_msu_searches=3):
    i = 0
    bot = Agent(system_prompt)
    max_wikipedia_calls = 1
    wikipedia_calls = 0
    msu_searches = 0

    if max_turns <= 0:
        return

    try:
        # Deterministic first step: use Wikipedia once for concepts/keywords.
        i += 1
        first_thought = "I need general concepts and keywords before searching MSU expertise."
        action = "wikipedia"
        action_input = question
        yield 'thought', first_thought
        yield 'action', f"{action}: {action_input}"

        observation = known_actions[action](action_input)
        wikipedia_calls += 1
        yield 'observation', observation

        # Preserve the same chat-message convention used by Agent.__call__.
        bot.messages.append({"role": "user", "content": question})
        bot.messages.append({"role": "assistant", "content": f"Thought: {first_thought}\nAction: {action}: {action_input}"})
        next_prompt = f"Observation: {observation}\n\nUse search_msu_expertise next with one focused keyword query."

        while i < max_turns:
            i += 1
            result = bot(next_prompt)
            # Split the response to find thoughts and actions
            lines = result.split('\n')
            parsed_action = None

            for line in lines:
                if line.startswith('Thought:'):
                    yield 'thought', line[8:].strip()
                elif line.startswith('Action:'):
                    yield 'action', line[7:].strip()
                    action_match = action_re.match(line)
                    if action_match and parsed_action is None:
                        parsed_action = action_match
                else:
                    yield 'response', line.strip()

            if not parsed_action:
                return

            action, action_input = parsed_action.groups()
            if action not in known_actions:
                raise Exception(f"Unknown action: {action}: {action_input}")

            if action == "wikipedia":
                if wikipedia_calls >= max_wikipedia_calls:
                    observation = {"error": "Wikipedia has already been used. Use search_msu_expertise next."}
                    yield 'observation', observation
                    next_prompt = f"Observation: {observation}"
                    continue
                wikipedia_calls += 1

            if action == "search_msu_expertise":
                if msu_searches >= max_msu_searches:
                    observation = {"error": f"Maximum search_msu_expertise calls reached ({max_msu_searches}). Answer from existing observations."}
                    yield 'observation', observation
                    next_prompt = f"Observation: {observation}"
                    continue
                msu_searches += 1

            observation = known_actions[action](action_input)
            yield 'observation', observation
            next_prompt = f"Observation: {observation}"

    except Exception as e:
        yield 'error', str(e)
        return

def wikipedia(query):
    """Fetches one Wikipedia page summary for keyword and term extraction.

    Args:
      query: The search query for Wikipedia.

    Returns:
      A dictionary with title, description, extract, and keywords_hint, or an error.
    """
    query = query.strip()
    if not query:
        return {"error": "Wikipedia query is empty"}

    headers = {
        "User-Agent": "MSUResearchAgent/0.1 (https://www.montana.edu/)",
        "Accept": "application/json"
    }

    params = {
        "action": "query",
        "generator": "search",
        "gsrsearch": query,
        "gsrlimit": 1,
        "prop": "extracts|pageterms",
        "exintro": 1,
        "explaintext": 1,
        "exsentences": 3,
        "wbptterms": "description",
        "format": "json",
        "formatversion": 2
    }

    try:
        response = httpx.get(
            "https://en.wikipedia.org/w/api.php",
            params=params,
            headers=headers,
            timeout=10.0
        )
    except httpx.RequestError as e:
        return {"error": f"Error connecting to Wikipedia: {e}"}

    if not response.is_success:
        return {"error": f"Error fetching Wikipedia data: {response.status_code} {response.reason_phrase}"}

    try:
        data = response.json()
    except json.JSONDecodeError:
        return {"error": "Invalid JSON response from Wikipedia"}

    pages = data.get("query", {}).get("pages", [])
    if not pages:
        return {"error": f"No Wikipedia results found for '{query}'"}

    page = pages[0]
    description = ""
    descriptions = page.get("terms", {}).get("description", [])
    if descriptions:
        description = descriptions[0]

    return {
        "title": page.get("title", ""),
        "description": description,
        "extract": page.get("extract", ""),
        "keywords_hint": "Use the title, description, and extract to choose 2-4 focused search_msu_expertise keyword queries."
    }

def search_msu_expertise(query):
    """Performs a search for MSU expertise and researcher interests.

    Args:
      query: The search query in the custom search engine.

    Returns:
      A dictionary containing a list of dictionaries, where each inner
      dictionary contains 'title', 'link', 'snippets', and 'description'
      for each search result.
    """
    # Set up your own Discovery Engine and Vertex AI Search
    #https://docs.cloud.google.com/generative-ai-app-builder/docs/migrate-from-cse
    projectID = 'expertise-finder-351604'
    agentID = 'msu-expertise-finder-ai_1731776759855'
    apiKey = 'AIzaSyDmI5BzQEaaylecXJiaSg86G4yiO_WBZcQ'

    url = f"https://discoveryengine.googleapis.com/v1/projects/{projectID}/locations/global/collections/default_collection/engines/{agentID}/servingConfigs/default_search:searchLite?key={apiKey}"

    data = {
        "servingConfig": f"projects/{projectID}/locations/global/collections/default_collection/engines/{agentID}/servingConfigs/default_search",
        "query": query,
        "contentSearchSpec": {
            "summarySpec": {
                "summaryResultCount": 3,
                "includeCitations": True
            },
            "extractiveContentSpec": {
                "maxExtractiveAnswerCount": 1
            }
        }
    }

    response = httpx.post(url, json=data)

    if not response.is_success:
        return {"error": f"Error fetching Google Search results: {response.status_code} {response.reason_phrase}"}

    try:
        decoded_response = response.json()
    except json.JSONDecodeError:
        return {"error": "Invalid JSON response from Google Search"}

    # Extract and format search results
    results = []
    for result in decoded_response.get('results', []):
        document = result.get('document', {})
        derived_data = document.get('derivedStructData', {})
        struct_data = document.get('structData', {})
        snippets = []

        for snippet in derived_data.get('snippets', []):
            snippet_text = snippet.get('snippet') or snippet.get('htmlSnippet')
            if snippet_text:
                snippets.append(snippet_text)

        extracted_result = {
            'title': derived_data.get('title') or struct_data.get('title', ''),
            'link': derived_data.get('link') or struct_data.get('link', ''),
            'snippets': snippets,
            'description': derived_data.get('description') or struct_data.get('description', '')
        }
        results.append(extracted_result)

    return {'results': results}

known_actions = {
    "wikipedia": wikipedia,
    "search_msu_expertise": search_msu_expertise
}