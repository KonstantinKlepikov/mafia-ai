import asyncio
import json
import subprocess
from typing import Any

from loguru import logger

from .schemas.llm_schemas import GenerateRequest, GenerateResponse, Usage


class OllamaRunner:
    """Executes Ollama model inference via subprocess.

    Args:
        binary_path: Path to ollama binary (default: 'ollama' from PATH).
        model_name: Name of the model to use (e.g. 'llama3.1:8b').
        timeout: Timeout in seconds for each subprocess call.
        pool_size: Number of concurrent subprocess executions.

    """

    def __init__(
        self,
        binary_path: str,
        model_name: str,
        timeout: int,
        pool_size: int,
    ) -> None:
        self._binary_path = binary_path
        self._model_name = model_name
        self._timeout = timeout
        self._pool_size = max(1, pool_size)

        # Semaphore to limit concurrent subprocess calls
        self._semaphore = asyncio.Semaphore(self._pool_size)

        logger.info(
            f'OllamaRunner initialized: {self._pool_size} concurrent '
            f'processes for {model_name}, timeout={timeout}s'
        )

    async def generate(self, request: GenerateRequest) -> GenerateResponse:
        """Generate response using ollama subprocess.

        Args:
            request: Generation request with system prompt and messages.

        Returns:
            Generated response with text and token usage.

        Raises:
            subprocess.TimeoutExpired: If subprocess exceeds timeout.
            RuntimeError: If subprocess returns non-zero exit code.

        """
        async with self._semaphore:
            return await self._call_ollama_subprocess(request)

    async def _call_ollama_subprocess(
        self, request: GenerateRequest
    ) -> GenerateResponse:
        """Execute ollama via subprocess.

        Uses `ollama run <model> --format json` with prompt via stdin.

        Args:
            request: Generation request.

        Returns:
            Generated response with text and token usage.

        """
        # Build full prompt: system + messages
        prompt_parts: list[str] = [f'System: {request.system_prompt}', '']

        for msg in request.messages:
            role_prefix = msg.role.capitalize()
            prompt_parts.append(f'{role_prefix}: {msg.content}')

        # Add final assistant prompt to trigger generation
        prompt_parts.append('Assistant:')

        full_prompt = '\n'.join(prompt_parts)

        # Run ollama in a thread pool to avoid blocking event loop
        result = await asyncio.to_thread(
            self._run_ollama_sync, full_prompt, request.max_tokens
        )

        return result

    def _run_ollama_sync(self, prompt: str, max_tokens: int) -> GenerateResponse:
        """Synchronous subprocess execution of ollama.

        Args:
            prompt: Full prompt text.
            max_tokens: Maximum tokens to generate.

        Returns:
            Generated response.

        Raises:
            subprocess.TimeoutExpired: If subprocess exceeds timeout.
            RuntimeError: If subprocess returns non-zero exit code or parsing fails.

        """
        cmd = [
            self._binary_path,
            'run',
            self._model_name,
            '--format',
            'json',
        ]

        # Build options JSON for ollama
        options: dict[str, Any] = {'num_predict': max_tokens}
        options_json = json.dumps(options)

        # Build final prompt with options
        full_input = f'{prompt}\n\nOptions: {options_json}'

        try:
            logger.debug(
                f'Running ollama subprocess: {" ".join(cmd[:3])} '
                f'(timeout={self._timeout}s, max_tokens={max_tokens})'
            )

            # Execute subprocess with timeout
            result = subprocess.run(
                cmd,
                input=full_input,
                capture_output=True,
                text=True,
                timeout=self._timeout,
                check=False,
            )

            if result.returncode != 0:
                error_msg = result.stderr.strip() or result.stdout.strip()
                logger.error(
                    f'Ollama subprocess failed (exit {result.returncode}): {error_msg}'
                )
                raise RuntimeError(
                    f'Ollama subprocess failed: {error_msg or "unknown error"}'
                )

            # Parse output - ollama outputs JSON lines, take the last one
            output_text = result.stdout.strip()

            if not output_text:
                raise RuntimeError('Ollama subprocess produced no output')

            # Try parsing as JSON (ollama --format json)
            try:
                lines = output_text.split('\n')
                # Find last line with valid JSON
                response_data = None
                for line in reversed(lines):
                    line = line.strip()
                    if line.startswith('{') and line.endswith('}'):
                        response_data = json.loads(line)
                        break

                if not response_data:
                    # Fallback: use raw output as text
                    generated_text = output_text
                    prompt_tokens = len(prompt.split())
                    completion_tokens = len(generated_text.split())
                else:
                    # Extract text from JSON response
                    generated_text = response_data.get('response', output_text)
                    prompt_tokens = response_data.get(
                        'prompt_eval_count', len(prompt.split())
                    )
                    completion_tokens = response_data.get(
                        'eval_count', len(generated_text.split())
                    )

            except json.JSONDecodeError as err:
                logger.warning(
                    f'Failed to parse ollama JSON output: {err}. Using raw output.'
                )
                generated_text = output_text
                prompt_tokens = len(prompt.split())
                completion_tokens = len(generated_text.split())

            logger.debug(
                f'Ollama generated {completion_tokens} tokens (prompt: {prompt_tokens})'
            )

            return GenerateResponse(
                text=generated_text,
                usage=Usage(
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_tokens=prompt_tokens + completion_tokens,
                ),
            )

        except subprocess.TimeoutExpired as err:
            logger.error(f'Ollama subprocess timed out after {self._timeout}s: {err}')
            raise

    async def close(self) -> None:
        """Cleanup resources (no-op for subprocess executor)."""
        logger.info('OllamaRunner closed')
