import time
import ollama


def measure_tps_repeated(
    model_name: str,
    prompt: str,
    num_tokens: int = 1000,
    repeats: int = 5,
) -> float:
    """
    Измеряет TPS с повторными запусками для повышения точности.
    """
    total_time = 0.0
    for i in range(repeats):
        print(f'Check {i} from {repeats} starts')
        start_time = time.time()
        ollama.generate(
            model=model_name,
            prompt=prompt,
            options={'num_predict': num_tokens, 'stream': False},
        )
        total_time += time.time() - start_time
        print(f'Check {i} from {repeats} ends')

    avg_time = total_time / repeats
    tps = num_tokens / avg_time
    return tps


if __name__ == '__main__':
    tps = measure_tps_repeated(
        'ministral-3:latest',
        'Explain quantum computing in simple terms.',
        num_tokens=500,
        repeats=10,
    )
    print(f'Средний TPS: {tps:.2f}')
