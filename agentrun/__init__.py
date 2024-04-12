"""AgentRun - Run Python code in an isolated Docker container"""

import ast
import os
import sys
import tarfile
from io import BytesIO
from threading import Thread
from typing import Any, Union
from uuid import uuid4

import docker
from docker.models.containers import Container
from RestrictedPython import compile_restricted


class AgentRun:
    """Class to execute Python code in an isolated Docker container.

    Example usage:
        from agentrun import AgentRun
        runner = AgentRun(container_name="my_container") # container should be running
        result = runner.execute_code_in_container("print('Hello, world!')")
        print(result)

    Args:
        container_name: Name of the Docker container to use
        dependencies_whitelist: List of whitelisted dependencies to install. By default, all dependencies are allowed.
        cpu_quota: CPU quota in microseconds (default: 50,000)
        default_timeout: Default timeout in seconds (default: 20)
        memory_limit: Memory limit for the container (default: 100m)
        memswap_limit: Memory + swap limit for the container (default: 512m)
        client: Docker client object (default: docker.from_env())
    """

    def __init__(
        self,
        container_name,
        dependencies_whitelist=["*"],
        cpu_quota=50000,
        default_timeout=20,
        memory_limit="100m",
        memswap_limit="512m",
        client=None,
    ):

        self.cpu_quota = cpu_quota
        self.default_timeout = default_timeout
        self.memory_limit = memory_limit
        self.memswap_limit = memswap_limit
        self.container_name = container_name
        self.dependencies_whitelist = dependencies_whitelist
        # this is to allow a mock client to be passed in for testing if docker is not available (not implemented yet)
        self.client = client or docker.from_env()

    class CommandTimeout(Exception):
        pass

    def execute_command_in_container(
        self, container: Container, cmd: str, timeout: int
    ) -> tuple[Any | None, Any | str]:
        """Execute a command in a Docker container with a timeout.

        This function runs the command in a separate thread and waits for the specified timeout.

        Args:
            container: Docker container object
            command: Command to execute
            timeout: Timeout in seconds
        Returns:
            Tuple of exit code and output

        """
        exit_code, output = None, None

        def target():
            nonlocal exit_code, output
            exec_log = container.exec_run(cmd=cmd, workdir="/code")
            exit_code, output = exec_log.exit_code, exec_log.output

        thread = Thread(target=target)
        thread.start()
        thread.join(timeout)
        if thread.is_alive():
            thread.join(1)
            raise self.CommandTimeout("Command timed out")
        output = output if output is not None else b""
        return exit_code, output.decode("utf-8")

    def safety_check(self, python_code: str) -> dict[str, object]:
        """Check if Python code is safe to execute.
        This function uses common patterns and RestrictedPython to check for unsafe patterns in the code.

        Args:
            python_code: Python code to check
        Returns:
            Dictionary with "safe" (bool) and "message" (str) keys
        """
        result = {"safe": True, "message": "The code is safe to execute."}

        # Crude check for problematic code (os, sys, subprocess, exec, eval, etc.)
        unsafe_modules = {"os", "sys", "subprocess", "builtins"}
        unsafe_functions = {
            "exec",
            "eval",
            "compile",
            "open",
            "input",
            "__import__",
            "getattr",
            "setattr",
            "delattr",
            "hasattr",
        }
        dangerous_builtins = {
            "globals",
            "locals",
            "vars",
            "dir",
            "eval",
            "exec",
            "compile",
        }
        # this a crude check first - no need to compile the code if it's obviously unsafe. Performance boost.
        try:
            tree = ast.parse(python_code)
        except SyntaxError as e:
            return {"safe": False, "message": f"Syntax error: {str(e)}"}

        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id in dangerous_builtins
            ):
                return {
                    "safe": False,
                    "message": f"Use of dangerous built-in function: {node.func.id}",
                }
            # Check for unsafe imports
            if isinstance(node, ast.Import) or isinstance(node, ast.ImportFrom):
                module_name = node.module if isinstance(node, ast.ImportFrom) else None
                for alias in node.names:
                    if module_name and module_name.split(".")[0] in unsafe_modules:
                        return {
                            "safe": False,
                            "message": f"Unsafe module import: {module_name}",
                        }
                    if alias.name.split(".")[0] in unsafe_modules:
                        return {
                            "safe": False,
                            "message": f"Unsafe module import: {alias.name}",
                        }
            # Check for unsafe function calls
            elif isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and node.func.id in unsafe_functions:
                    return {
                        "safe": False,
                        "message": f"Unsafe function call: {node.func.id}",
                    }
                elif (
                    isinstance(node.func, ast.Attribute)
                    and node.func.attr in unsafe_functions
                ):
                    return {
                        "safe": False,
                        "message": f"Unsafe function call: {node.func.attr}",
                    }

        try:
            # Compile the code using RestrictedPython with a filename indicating its dynamic nature
            compiled_code = compile_restricted(
                python_code, filename="<dynamic>", mode="exec"
            )
            # Note: Execution step is omitted to only check the code without running it
            # This is not perfect, but should catch most unsafe patterns
        except Exception as e:
            return {
                "safe": False,
                "message": f"RestrictedPython detected an unsafe pattern: {str(e)}",
            }

        return result

    def parse_dependencies(self, python_code: str) -> list[str]:
        """Parse Python code to find import statements and filter out standard library modules.
        This function returns a list of unique dependencies found in the code.

        Args:
            python_code: Python code to parse
        Returns:
            List of unique dependencies
        """
        tree = ast.parse(python_code)
        dependencies = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    # Get the base module name. E.g. for "import foo.bar", it's "foo"
                    module_name = alias.name.split(".")[0]
                    if (
                        module_name not in sys.stdlib_module_names
                        and module_name not in sys.builtin_module_names
                    ):
                        dependencies.append(module_name)
            elif isinstance(node, ast.ImportFrom):
                module_name = node.module.split(".")[0] if node.module else ""
                if (
                    module_name
                    and module_name not in sys.stdlib_module_names
                    and module_name not in sys.builtin_module_names
                ):
                    dependencies.append(module_name)
        return list(set(dependencies))  # Return unique dependencies

    def install_dependencies(self, container: Container, dependencies: list) -> str:
        """Install dependencies in the container.
        Args:
            container: Docker container object
            dependencies: List of dependencies to install
        Returns:
            Success message or error message

        """
        everything_whitelisted = "*" in self.dependencies_whitelist

        # Perform a pre-check to ensure all dependencies are in the whitelist (or everything is whitelisted)
        if not everything_whitelisted:
            for dep in dependencies:
                if dep not in self.dependencies_whitelist:
                    return f"Dependency: {dep} is not in the whitelist."

        for dep in dependencies:
            command = f"pip install --user {dep}"
            exit_code, output = self.execute_command_in_container(
                container, command, timeout=120
            )
            if exit_code != 0:
                return f"Failed to install dependency {dep}"

        return "Dependencies installed successfully."

    def uninstall_dependencies(self, container: Container, dependencies: list) -> str:
        """Uninstall dependencies in the container.
        Args:
            container: Docker container object
            dependencies: List of dependencies to uninstall
        Returns:
            Success message or error message
        """
        for dep in dependencies:
            command = f"pip uninstall -y {dep}"
            exit_code, output = self.execute_command_in_container(
                container, command, timeout=120
            )

        return "Dependencies uninstalled successfully."

    def copy_code_to_container(
        self, container: Container, python_code: str
    ) -> dict[str, Union[bool, str]]:
        """Copy Python code to the container.
        Args:
            container: Docker container object
            python_code: Python code to copy
        Returns:
            Success message or error message
        """
        result = {"success": False, "message": ""}
        script_name = f"script_{uuid4().hex}.py"
        temp_script_path = os.path.join("/tmp", script_name)

        with open(temp_script_path, "w") as file:
            file.write(python_code)

        tar_stream = BytesIO()
        with tarfile.open(fileobj=tar_stream, mode="w") as tar:
            tar.add(temp_script_path, arcname=script_name)
        tar_stream.seek(0)

        exec_result = container.put_archive(path="/code/", data=tar_stream)
        if exec_result:
            return {"success": True, "message": script_name}

        return {"success": False, "message": "Failed to copy script to container."}

    def clean_up(
        self, container: Container, script_name: str, dependencies: list
    ) -> None:
        """Clean up the container after execution.
        Args:
            container: Docker container object
            script_name: Name of the script to remove
        """
        if script_name:
            os.remove(os.path.join("/tmp", script_name))
            container.exec_run(cmd=f"rm /code/{script_name}", workdir="/code")
            dep_uninstall_result = self.uninstall_dependencies(container, dependencies)
        return None

    def execute_code_in_container(self, python_code: str) -> str:
        """Executes Python code in an isolated Docker container.
        This is the main function to execute Python code in a Docker container. It performs the following steps:
        1. Check if the code is safe to execute
        2. Update the container with the memory limits
        3. Copy the code to the container
        4. Install dependencies in the container
        5. Execute the code in the container
        5. Uninstall dependencies in the container & clean up

        Args:
            python_code: Python code to execute
        Returns:
            Output of the code execution or an error message
        """
        try:
            output = ""
            client = self.client
            timeout_seconds = self.default_timeout
            container = None

            # check  if the code is safe to execute
            safety_result = self.safety_check(python_code)
            safety_message = safety_result["message"]
            safe = safety_result["safe"]
            if not safe:
                return safety_message

            try:
                container = client.containers.get(self.container_name)
            except docker.errors.NotFound:
                return f"Container with name {self.container_name} not found."
            # update the container with the new limits
            container.update(
                cpu_quota=self.cpu_quota,
                mem_limit=self.memory_limit,
                memswap_limit=self.memswap_limit,
            )
            # Copy the code to the container
            exec_result = self.copy_code_to_container(container, python_code)
            successful_copy = exec_result["success"]
            copy_message = exec_result["message"]
            if not successful_copy:
                copy_message = exec_result["message"]
                return copy_message

            script_name = copy_message

            # Install dependencies in the container
            dependencies = self.parse_dependencies(python_code)
            dep_install_result = self.install_dependencies(container, dependencies)
            if dep_install_result != "Dependencies installed successfully.":
                return dep_install_result

            try:
                _, output = self.execute_command_in_container(
                    container, f"python /code/{script_name}", timeout_seconds
                )
            except self.CommandTimeout:
                return "Execution timed out."

        except Exception as e:
            return str(e)

        finally:
            if container:
                self.clean_up(container, script_name, dependencies)

        return output
