import asyncio, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

# Временно переопределяем — только 1 запрос, только top_k=10
import eval_runner
eval_runner.QUERIES = {
    "cs": ["knowledge graph embedding methods"],
    "math": ["matrix decomposition methods"],
    "physics": ["black hole thermodynamics"],
}
eval_runner.TOP_K_VALUES = [10]

asyncio.run(eval_runner.main())