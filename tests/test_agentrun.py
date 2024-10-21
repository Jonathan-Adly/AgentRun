import os

import docker
import pytest

from agentrun import AgentRun


@pytest.fixture(scope="session")
def docker_container():
    client = docker.from_env()

    # Gets the directory of the current file (test_agentrun.py)
    current_dir = os.path.dirname(__file__)
    # Navigate to 'agentrun/agentrun/'
    agentrun_path = os.path.abspath(os.path.join(current_dir, "..", "agentrun"))

    # Run a container with the Python image
    container = client.containers.run(
        "python:3.12.2-slim-bullseye",
        name="test-container",
        detach=True,
        volumes={agentrun_path: {"bind": "/code", "mode": "rw"}},
        command=["tail", "-f", "/dev/null"],  # Keep the container running
        pids_limit=10,
        security_opt=["no-new-privileges:true"],
    )

    yield container  # Provide the container to the test

    # Cleanup: Stop and remove the container
    container.stop()
    container.remove()


@pytest.mark.parametrize(
    "code, expected",
    [
        (
            "print('Hello, World!')",
            {"safe": True, "message": "The code is safe to execute."},
        ),
        (
            "print('Hello, World!'",
            {
                "safe": False,
                "message": "Syntax error: '(' was never closed (<unknown>, line 1)",
            },
        ),
        (
            "import os.path\nprint(os.path.join('dir', 'file.txt'))",
            {"safe": False, "message": "Unsafe module import: os.path"},
        ),
        (
            "from os import path\nprint(path.join('dir', 'file.txt'))",
            {"safe": False, "message": "Unsafe module import: os"},
        ),
        (
            "class MyClass:\n    def __init__(self):\n        self.eval = eval\n\nobj = MyClass()\nobj.eval('print(\"Hello, World!\")')",
            {"safe": False, "message": "Unsafe function call: eval"},
        ),
        (
            "def my_function():\n    pass\n\nmy_function.__globals__['__builtins__']['eval']('print(\"Hello, World!\")')",
            {
                "safe": False,
                "message": 'RestrictedPython detected an unsafe pattern: (\'Line 4: "__globals__" is an invalid attribute name because it starts with "_".\',)',
            },
        ),
        (
            "import os\nos.system('rm -rf /')",
            {"safe": False, "message": "Unsafe module import: os"},
        ),
        (
            "mod_name = 'os'\n__import__(mod_name).system('ls')",
            {"safe": False, "message": "Unsafe function call: __import__"},
        ),
        (
            "exec('import os\\nos.system(\\'ls\\')')",
            {"safe": False, "message": "Use of dangerous built-in function: exec"},
        ),
        (
            "eval('os.system(\\'ls\\')', {'os': __import__('os')})",
            {"safe": False, "message": "Use of dangerous built-in function: eval"},
        ),
        (
            "globals()[chr(111)+chr(115)].system('rm -rf / --no-preserve-root')",
            {"safe": False, "message": "Use of dangerous built-in function: globals"},
        ),
        (
            "import os\nprint('This is safe')\nos.system('ls')",
            {"safe": False, "message": "Unsafe module import: os"},
        ),
        # fails restritive python. It is (safe?) for our machine, but not for other people's machine.
        (
            "import socket\ns = socket.socket(socket.AF_INET, socket.SOCK_STREAM)\ns.connect(('example.com', 80))",
            {"safe": True, "message": "The code is safe to execute."},
        ),
        (
            "with open('secret_file.txt', 'r') as file:\n    print(file.read())",
            {"safe": False, "message": "Unsafe function call: open"},
        ),
        (
            "import subprocess\nsubprocess.Popen(['ping', '-c', '4', 'example.com'])",
            {"safe": False, "message": "Unsafe module import: subprocess"},
        ),
    ],
)
def test_safety_check(code, expected, docker_container):
    runner = AgentRun(
        container_name=docker_container.name,
    )
    result = runner.safety_check(code)
    assert result["safe"] == expected["safe"]
    assert result["message"] == expected["message"]


@pytest.mark.parametrize(
    "code, expected",
    [
        (
            "print('Hello, World!')",
            "Hello, World!\n",
        ),
        (
            "import time\ntime.sleep(3)",
            "Execution timed out.",
        ),
    ],
)
def test_execute_code_with_timeout(code, expected, docker_container):

    runner = AgentRun(
        default_timeout=1,
        container_name="test-container",
    )
    output = runner.execute_code_in_container(python_code=code)
    assert output == expected


@pytest.mark.parametrize(
    "code, expected",
    [
        ("import os", []),
        ("import requests", ["requests"]),
        ("from collections import namedtuple", []),
        ("import sys\nimport numpy as np", ["numpy"]),
        ("import unknownpackage", ["unknownpackage"]),
        ("from scipy.optimize import minimize", ["scipy"]),
    ],
)
def test_parse_dependencies(code, expected, docker_container):
    runner = AgentRun(
        container_name=docker_container.name,
    )
    result = runner.parse_dependencies(code)

    assert sorted(result) == sorted(expected)


@pytest.mark.parametrize(
    "code, expected, whitelist, cached",
    [
        # dependencies: arrow, open whitelist
        (
            "import arrow\nfixed_date = arrow.get('2023-04-15T12:00:00')\nprint(fixed_date.format('YYYY-MM-DD HH:mm:ss'))",
            "2023-04-15 12:00:00\n",
            ["*"],
            ["requests"],
        ),
        # dependencies: numpy, but not in the whitelist
        (
            "import numpy as np\nprint(np.array([1, 2, 3]))",
            "Dependency: numpy is not in the whitelist.",
            ["pandas"],
            [],
        ),
        # python built-in
        ("import math\nprint(math.sqrt(16))", "4.0\n", ["requests"], []),
        # dependencies: requests, in the whitelist
        (
            "import numpy as np\nprint(np.array([1, 2, 3]))",
            "[1 2 3]\n",
            ["numpy"],
            ["numpy"],
        ),
        # a dependency that doesn't exist
        (
            "import unknownpackage",
            "Failed to install dependency unknownpackage",
            ["*"],
            [],
        ),
    ],
)
def test_execute_code_with_dependencies(
    code, expected, whitelist, cached, docker_container
):
    runner = AgentRun(
        container_name=docker_container.name,
        dependencies_whitelist=whitelist,
        cached_dependencies=cached,
    )
    output = runner.execute_code_in_container(code)
    assert output == expected


@pytest.mark.parametrize(
    "code, expected",
    [
        (
            "print('Hello, World!')",
            "Hello, World!\n",
        ),
        ("import os\nos.system('rm -rf /')", "Unsafe module import: os"),
    ],
)
def test_execute_code_in_container(code, expected, docker_container):
    runner = AgentRun(
        container_name=docker_container.name,
    )
    output = runner.execute_code_in_container(code)
    assert output == expected


def test_init_with_wrong_container_name(docker_container):
    with pytest.raises(ValueError) as excinfo:
        runner = AgentRun(container_name="wrong-container-name")

    assert "Container wrong-container-name not found" in str(excinfo.value)


def test_init_with_stopped_container(docker_container):
    # stop the docker_container
    docker_container.stop()
    with pytest.raises(ValueError) as excinfo:
        runner = AgentRun(container_name=docker_container.name)

    assert f"Container {docker_container.name} is not running."
    docker_container.start()


def test_init_with_docker_not_running():
    from unittest.mock import Mock, patch

    # Create a mock client that raises an exception when ping is called
    with patch("docker.DockerClient") as MockClient:
        mock_client = MockClient.return_value
        mock_client.ping.side_effect = docker.errors.DockerException(
            "Docker daemon not available"
        )

        # Test that initializing AgentRun with this mock client raises ValueError
        with pytest.raises(RuntimeError) as excinfo:
            runner = AgentRun(container_name="any-name", client=mock_client)

        assert (
            "Failed to connect to Docker daemon. Please make sure Docker is running. Docker daemon not available"
            in str(excinfo.value)
        )


def test_init_w_dependency_mismatch(docker_container):
    with pytest.raises(ValueError) as excinfo:
        runner = AgentRun(
            container_name=docker_container.name,
            dependencies_whitelist=[],
            cached_dependencies=["requests"],
        )
    assert "Some cached dependencies are not in the whitelist." in str(excinfo.value)


"""**benchmarking**"""


def execute_code_in_container_benchmark(runner, code):
    output = runner.execute_code_in_container(code)
    return output


def test_cached_dependency_benchmark(benchmark, docker_container):
    runner = AgentRun(
        container_name=docker_container.name,
        cached_dependencies=["numpy"],
    )
    result = benchmark(
        execute_code_in_container_benchmark,
        runner=runner,
        code="import numpy as np\nprint(np.array([1, 2, 3]))",
    )
    assert result == "[1 2 3]\n"


def test_dependency_benchmark(benchmark, docker_container):
    runner = AgentRun(
        container_name=docker_container.name,
    )
    result = benchmark(
        execute_code_in_container_benchmark,
        runner=runner,
        # use requests
        code="import requests\nprint(requests.get('https://example.com').status_code)",
    )
    assert result == "200\n"


def test_exception_benchmark(benchmark, docker_container):
    runner = AgentRun(
        container_name=docker_container.name,
    )
    result = benchmark(
        execute_code_in_container_benchmark,
        runner=runner,
        code="print(f'{1/0}')",
    )
    ends_with = "ZeroDivisionError: division by zero\n"
    assert result.endswith(ends_with)


def test_vanilla_benchmark(benchmark, docker_container):
    runner = AgentRun(
        container_name=docker_container.name,
    )
    result = benchmark(
        execute_code_in_container_benchmark,
        runner=runner,
        code="print('Hello, World!')",
    )
    assert result == "Hello, World!\n"
