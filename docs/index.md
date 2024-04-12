# Agentrun : Run AI generated code safely

[![PyPI](https://img.shields.io/pypi/v/agentrun.svg)](https://pypi.org/project/agentrun/)
[![Tests](https://github.com/jonathan-adly/agentrun/actions/workflows/test.yml/badge.svg)](https://github.com/jonathan-adly/agentrun/actions/workflows/test.yml)
[![Changelog](https://img.shields.io/github/v/release/jonathan-adly/agentrun?include_prereleases&label=changelog)](https://github.com/jonathan-adly/agentrun/releases)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](https://github.com/jonathan-adly/agentrun/blob/main/LICENSE)
[![Twitter Follow](https://img.shields.io/twitter/follow/Jonathan_Adly_?style=social)](https://twitter.com/Jonathan_Adly_)

Agentrun is a Python library that makes it a breeze to run python code safely from large language models (LLMs) with a single line of code. Built on top of docker python SDK and RestrictedPython, it provides a simple, transparent, and user-friendly API to manage isolated code exeuction. 

Agentrun automatically install and uninstall dependencies, limits resource consumption, checks code safety, and set execution timeouts. It has >97% test coverage with full static typing and only 2 dependecies. 

## Key Features

- **Safe code execution**: Agentrun checks the generated code for dangerous elements before execution
- **Isolated Environment**: Code is executed in a fully isolated docker container
- **Configurable Resource Management**: You can set how much compute resources the code can consume, with sane defaults
- **Timeouts**: Set time limits on how long a script can take to run 
- **Dependency Management**: Complete control on what dependencies are allowed to install
- **Automatic Cleanups**: Agentrun cleans any artificats created by the code generated 
- **Comes with a REST API**: Hate setting up docker? Agentrun comes with already configured docker setup for self-hosting.


If you want to use your own docker configuration, use this package. If you want an already configured docker setup and API that is ready for self-hosting. Please see here: https://github.com/Jonathan-Adly/agentrun-api

**We Highly recommend using the REST API with already configured docker as a standalone service. It is available here: https://github.com/Jonathan-Adly/agentrun-api** 

## Get Started in Minutes

There are two ways to use agentrun - depending on your needs. With pip if you want to use your own docker setup, or you can directly use it as a rest API as a standalone service (recommended).

1. Install Agentrun with a single command via pip (you will need to configure your own docker setup)

```bash
pip install agentrun
```

Now, let's see AgentRun in action with a simple example:

```Python
from agentrun import AgentRun

runner = AgentRun(container_name="my_container") # container should be running
code_from_llm = get_code_from_llm(prompt) # "print('hello, world!')"

result = runner.execute_code_in_container(code_from_llm)
print(result)
#> "Hello, world!" 
```

Worried about spinning up docker containers? No problem. 

2. Install the agentrun REST api from github and get going immediately
```bash
git clone https://github.com/Jonathan-Adly/agentrun-api
cd agentrun-api
cp .example.env .dev.env
docker-compose up -d --build
```

Then - you have a fully up and running code execution API. *Code in --> output out* 

```javascript
fetch('http://localhost:8000/v1/run/', {
    method: 'POST',
    headers: {
        'Content-Type': 'application/json'
    },
    body: JSON.stringify({
        code: "print('hello, world!')"
    })
})
.then(response => response.json())
.then(data => console.log(data))
.catch(error => console.error('Error:', error));
```

Or if you prefer the terminal. 

`curl -X POST http://localhost:8000/v1/run/ -H "Content-Type: application/json" -d '{"code": "print(\'hello, world!\')"}'`


Difference  | Python Package            | REST API              |
---------   | --------------            | -----------           |
Docker setup| You set it up             | Already setup for you |       
Installation| Pip                       | Git clone             |
Ease of use | Easy                      | Super Easy            |
Requirements| A running docker container| Docker installed      |
Customize   | Fully                     | Partially             |



## Usage

Now, let's see AgentRun in action with something more complicated. We will take advantage of function calling and agentrun, to have LLMs write and execute code on the fly to solve arbitrary tasks. You can find the full code under `examples/function_calling.py`

We are using the REST API as it is recommend to seperate the code execution service from the rest of our infrastructure.

1. Install needed packages. 
```bash
pip install openai requests
```
> We are using openai her to keep the code simple with minimal depenencies, but agentrun works with any LLM out of the box. All what's required is for the LLM to return a code snippet.
>
> FYI: OpenAI assistant tool ` code_interpreter` can execute code. Agentrun is a transparent, open-source version that can work with any LLM.

2. Setup a function that executed the code and returns an output.
```python
def execute_python_code(code: str) -> str:
    response = requests.post("http://localhost:8000/v1/run/", json={"code": code})
    output = response.json()["output"]
    return output
```

3. Setup your LLM function calling.

```python
GPT_MODEL = "gpt-4-turbo-preview"

# set your API key here.
os.environ["OPENAI_API_KEY"] = "Your OpenAI key here"

client = OpenAI()

tools = [
    {
        "type": "function",
        "function": {
            "name": "execute_python_code",
            "description": "Sends a python code snippet to the code execution environment and returns the output. The code execution environment can automatically import any library or package by importing.",
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
```

4. Setup a function to call your LLM of choice.
```python
def chat_completion_request(messages, tools=None, tool_choice=None, model=GPT_MODEL):
    try:
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            tools=tools,
            tool_choice=tool_choice,
        )
        return response
    except Exception as e:
        print("Unable to generate ChatCompletion response")
        print(f"Exception: {e}")
        return e
```

5. Pass on the user query and get the answer.
```python
def get_answer(query):
    messages = []
    messages.append(
        {
            "role": "system",
            "content": """Don't make assumptions about what values to plug into functions. Ask for clarification if a user request is ambiguous.\n 
            Use the execute_python_code tool to run code if a question is better solved with code. You can use any package in the code snippet by simply importing. Like `import requests` would work fine.\n
            """,
        }
    )
    messages.append({"role": "user", "content": query})

    chat_response = chat_completion_request(messages, tools=tools)

    message = chat_response.choices[0].message
    # tool call versus content
    if message.tool_calls:
        tool_call = message.tool_calls[0]
        arg = json.loads(tool_call.function.arguments)["code"]
        print(f"Executing code: {arg}")
        answer = execute_python_code(arg)
        # Optional: call an LLM again to turn the answer to a human friendly response
        query = "Help translate the code output to a human friendly response. This was the user query: " + query + " The code output is: " + answer
        answer = get_answer(query)
    else:
        answer = message.content

    return answer
```

Example Response:

- print (get_answer("what's the average daily move of Apple stock in the last 3 days?")) --> "The average daily movement of Apple's stock over the last 3 days was $2.39."

**How did get this answer?**

First, the LLM generated the code to call the Yahoo stock API (via yf) as such:

```Python
#AI generated
import yfinance as yf

# Setting the ticker and period for the last 3 days
apple = yf.Ticker('AAPL')
hist = apple.history(period="3d")

# Calculating daily moves (close - open) and their average
moves = hist['Close'] - hist['Open']
average_move = moves.mean()

print(f'{average_move:.2f}')
```

That code was sent to agentrun, which outputted: 
`'\r[*********************100%%**********************]  1 of 1 completed\n2.391396866861979\n'`

Lastly, the output was sent to the LLM again to make human friendly. Giving us the final answer: $2.39



## Customize

Agentrun has sane defaults, but totally customizable. You can change:

1. dependencies_whitelist - by default any thing that can be pip installed is allowable.
2. cpu_quota - the default is 50000. Here is GPT-4 explaining what does that mean.

> In Docker SDK, the cpu_quota parameter is used to limit CPU usage for a container. 
> The value of cpu_quota specifies the amount of CPU time that the container is allowed to use in microseconds per scheduling period. 
> The default scheduling period for Docker is 100 milliseconds (100,000 microseconds).
>
> If you set cpu_quota to 50000, this means that the container is allowed to use 50,000 microseconds of CPU time every 100 milliseconds. 
> Essentially, this limits the container to 50% CPU usage of a single CPU core during each scheduling period. 
> If your system has multiple cores, the container could still potentially use more total CPU resources by spreading the load across multiple cores.

3. default_timeout - how long is scripts allowed to run for. Default is 20 seconds.
4. memory_limit - how much memory can execution take. Default is 100mb 
5. memswap_limit - the default is 512mb. Again, here is GPT-4 explaing what memory_mit and memswap do. 

> In Docker SDK, the memswap_limit parameter is used to control the memory and swap usage of a container. 
> This setting specifies the maximum amount of combined memory and swap space that the container can use. The value is given in bytes.
> 
> Here’s how it works:

> - Memory (RAM): This is the actual physical memory that the container can use.
> - Swap: This is a portion of the hard drive that is used when the RAM is fully utilized. 
> Using swap allows the system to handle more memory allocation than the physical memory available, but accessing swap is significantly slower than accessing RAM.


You can change any of the defauts when you initalize AgentRun as below. 

```Python
from agentrun import AgentRun
# container should be running
runner = AgentRun(
container_name="my_container",
# only allowed to pip install requests
dependencies_whitelist = ["requests"], # [] = no dependencies
# 3 minutes timeout
default_timeout = 3 * 60,  
# how much RAM can the script use
memory_limit = "512mb" 
# how much total memory the script can use, using a portion of the hard drive that is used when the RAM is fully utilize
memswap_limit= "1gb" 
) 
code_from_llm = get_code_from_llm(prompt) # "print('hello, world!')"

result = runner.execute_code_in_container(code_from_llm)
print(result)
#> "Hello, world!" 
```

## Development

To contribute to this library, first checkout the code. Then create a new virtual environment:
```bash
cd agentrun
python -m venv venv
source venv/bin/activate
```
Now install the dependencies and test dependencies:
```bash
pip install -e '.[test]'
```
To run the tests:
```bash
pytest
```
