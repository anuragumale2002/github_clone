# PyGit Benchmarks

Simple timing benchmarks for PyGit. Run from **project root** with `PYTHONPATH=.`.

## Run

```bash
# All benchmarks (commits=100, files=500, clone=50 commits)
PYTHONPATH=. python -m bench.run

# One benchmark
PYTHONPATH=. python -m bench.run commits
PYTHONPATH=. python -m bench.run status
PYTHONPATH=. python -m bench.run clone

# Options
PYTHONPATH=. python -m bench.run commits -n 200
PYTHONPATH=. python -m bench.run status -f 1000
PYTHONPATH=. python -m bench.run clone -c 100
```

## Benchmarks

| Bench     | Description                         | Options        |
|-----------|-------------------------------------|----------------|
| `commits` | Time N commits (one file per commit) | `-n` (default 100) |
| `status`  | Time status with many tracked files | `-f` (default 500) |
| `clone`   | Time clone of local repo            | `-c` (default 50 commits) |

## Profiling

To profile PyGit (e.g. find hot paths):

- **cProfile:**  
  `PYTHONPATH=. python -m cProfile -o bench.prof -m bench.run commits -n 50`  
  Then: `python -m pstats bench.prof` or use `snakeviz bench.prof`.

- **py-spy** (if installed):  
  `py-spy record -o bench.svg -- python -m bench.run commits -n 50`

- **timeit** a single command:  
  `PYTHONPATH=. python -m timeit -n 5 -r 2 "import subprocess; subprocess.run(['python', '-m', 'pygit', 'status'], cwd='.', capture_output=True)"`

Temp dirs are created under the system temp and removed after each benchmark.
