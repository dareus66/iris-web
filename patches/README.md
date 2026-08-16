# Windows patches for iris.c

iris does not build on Windows as it stands. These three patches make
`make blas` work from an MSYS2 UCRT64 shell.

They are also proposed upstream as
[antirez/iris.c#52](https://github.com/antirez/iris.c/pull/52). **If that
pull request is merged, this folder is obsolete**: build the official
sources instead.

## Applying them

```bash
git clone https://github.com/antirez/iris.c
cd iris.c
git am /path/to/iris-web/patches/*.patch
```

Then, from an **MSYS2 UCRT64** shell (not "MSYS2 MSYS", which is a
different environment and will not build):

```bash
pacman -S mingw-w64-ucrt-x86_64-gcc mingw-w64-ucrt-x86_64-openblas make
make blas
```

The resulting `iris.exe` needs the UCRT64 DLLs, so either run it from
that shell or let `iris-web` find them — it looks in the usual places
and adds them to PATH by itself.

## What they change

1. **`pngtest: link jpeg.c`** — unrelated to Windows, and broken on every
   platform: `iris_image.c` calls `jpeg_load_mem()`/`jpeg_free()`, whose
   implementation lives in `jpeg.c`, which the target never compiled.
2. **`Windows: build with MinGW-w64 and OpenBLAS`** — the port itself.
   File mapping via `CreateFileMapping` instead of `mmap`, `GetSystemInfo`
   instead of `sysconf`, binary-mode `fopen` for config and tokenizer
   files, and the iTerm2 temp-file path disabled (MinGW has no
   `mkstemps`, and iTerm2 is never detected on Windows anyway).
3. **`Document the Windows build`** — AGENT.md and README.

Everything is inside `#ifdef _WIN32`. The POSIX branches are untouched,
so macOS and Linux behave exactly as before.

## What does not work on Windows

The interactive REPL is not built: `iris_cli.c`, `linenoise.c` and
`embcache.c` need termios. Asking for interactive mode prints an error
and exits. Terminal image previews compile but do not render.

## Verified

Built on a Xeon W-2125 with OpenBLAS 0.3.34 and gcc 16.2, checked against
the reference images in the iris repository — all well inside its
threshold of 20:

| Test | mean_diff |
|---|---|
| 64x64, 2 steps, seed 42 | 1.14 |
| 512x512, 4 steps, seed 123 | 2.12 |
| img2img 256x256, seed 456 | 8.29 |

`run_test.py --quick` passes as is. The full suite kills each test after
300s, which is not enough for the 512x512 case on a CPU this slow, so
those three were run by hand.
