import asyncio
import json
import subprocess
from typing import Any

from loguru import logger

from config import MafiaSettings
from schemas import GenerateRequest, GenerateResponse, Usage

from .resource_detection import calculate_pool_size, detect_hardware


class LLM:
    """Local Ollama inference via subprocess."""

    def __init__(self, settings: MafiaSettings) -> None:
        """Initialize LLM.

        Args:
            settings (MafiaSettings): Unified service settings.

        """
        self.settings = settings

        pool_size = settings.llm_pool_size
        if settings.llm_pool_size == 0:
            hardware = detect_hardware()
            pool_size = calculate_pool_size(hardware, settings.ollama_model)
            logger.info(f'Auto-detected pool size: {pool_size}')
        self._pool_size = max(1, pool_size)
        logger.info(f'Using pool size: {pool_size}')

        # Semaphore to limit concurrent subprocess calls
        self._semaphore = asyncio.Semaphore(self._pool_size)

        logger.info(
            f'LLM initialized: {self._pool_size} concurrent '
            f'processes for {settings.ollama_model}, timeout={settings.ollama_timeout}s'
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

        TODO: test semaphore

        """
        async with self._semaphore:
            return await self._call_ollama_subprocess(request)

    async def _call_ollama_subprocess(
        self,
        request: GenerateRequest,
    ) -> GenerateResponse:
        """Execute ollama via subprocess.

        Uses `ollama run <model> --format json` with prompt via stdin.

        Args:
            request (GenerateRequest): Generation request.

        Returns:
            GenerateRespons: generated response with text and token usage.

        TODO: test me

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
            self._run_ollama_sync,
            full_prompt,
            request.max_tokens,
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

        TODO: test me

        """
        cmd = [
            self.settings.ollama_binary_path,
            'run',
            self.settings.ollama_model,
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
                f'(timeout={self.settings.ollama_timeout}s, max_tokens={max_tokens})'
            )

            # Execute subprocess with timeout
            result = subprocess.run(
                cmd,
                input=full_input,
                capture_output=True,
                text=True,
                timeout=self.settings.ollama_timeout,
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
            logger.error(
                f'Ollama subprocess timed out after {self.settings.ollama_timeout}s: '
                f'{err.__str__()}'
            )
            raise
