""" This example illustrastes the use of the Ollama model with the dolphin-llama3 """

import json

# json_repair docs: https://pypi.org/project/json-repair/
import json_repair
import requests


# This function sends a python code snippet to the code execution environment and returns the output.
def execute_python_code(code: str) -> str:
    # make sure AgentRun is running on your local machine
    code = json.dumps({"code": code})
    response = requests.post(
        "http://localhost:8000/v1/run/",
        data=code,
        headers={"Content-Type": "application/json"},
    )
    print(code)
    output = response.json()["output"]
    return output


# Ollama dolphin-llama3 page: https://ollama.com/library/dolphin-llama3
MODEL = "dolphin-llama3"


tools = [
    {
        "type": "function",
        "function": {
            "name": "execute_python_code",
            "description": """Sends a python code snippet to the code execution environment and returns the output. 
            The code execution environment can automatically import any library or package by importing. 
            The code snippet to execute must be a valid python code and must use print() to output the result.""",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "The code snippet to execute. Must be a valid python code. Must use print() to output the result.",
                    },
                },
                "required": ["code"],
            },
        },
    },
]


# Code adapted from here: https://github.com/namuan/llm-playground/blob/main/local-llm-tools-simple.py
def generate_full_completion(prompt: str, model: str = MODEL) -> dict[str, str]:
    params = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        # deterministic output
        "temperature": 0,
        "seed": 123,
        "format": "json",
    }
    try:
        # Ollama API docs: https://github.com/ollama/ollama/blob/main/docs/api.md#request-json-mode
        response = requests.post(
            f"http://localhost:11434/api/generate",
            headers={"Content-Type": "application/json"},
            data=json.dumps(params),
            timeout=60,
        )
        # print(f"🤖 Request: {json.dumps(params)} -> Response: {response.text}")
        response.raise_for_status()
        return json_repair.loads(response.text)
    except requests.RequestException as err:
        return {"error": f"API call error: {str(err)}"}


def get_answer(query: str) -> str:
    functions_prompt = f"""
        You have access to the following tools:
            {tools}
        You must follow these instructions:
        If a user query requires a tool, you must select the appropriate tool from the list of tools provided.
        Always select one or more of the above tools based on the user query
        If a tool is found, you must respond in the JSON format matching the following schema:
        {{
        "tools": {{
            "tool": "<name of the selected tool>",
            "tool_input": <parameters for the selected tool, matching the tool's JSON schema
        }}
        }}
        If there are multiple tools required, make sure a list of tools are returned in a JSON array.
        If there is no tool that match the user request, you will respond with empty json.
        Do not add any additional Notes or Explanations.
        
        User Query: {query}
        """

    r_dict = generate_full_completion(functions_prompt)
    # print(f"Ollama Response: {r_dict}")
    r_tools = json_repair.loads(r_dict["response"])["tools"]
    arg = r_tools["tool_input"]
    code = arg["code"]
    # print(f"Executing code: {code}")
    response = execute_python_code(code)
    # print(f"Code Execution result: {response}")
    return response


# 3952152
print(get_answer("what's 12312 *321?"))
# 500
print(get_answer("how many even numbers are there between 1 and 1000?"))
# Paris
print(get_answer("what's the capital of France?"))
