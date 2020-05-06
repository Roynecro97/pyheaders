# pyheaders

C++ header (and source) parser for Python using Clang plugins.

## Installation

1. Get the required tools:

   - You'll need to have clang-10 and the required dev tools installed.

     To install using `apt` on Debian / Ubuntu see then [LLVM Debian/Ubuntu nightly packages](apt.llvm.org) page.

   - Note that _pyheaders_ requires Python>=3.8.

2. Clone pyheaders:

   Change the directory to where you want the _pyheaders_ installer directory placed.

   ```sh
   git clone https://github.com/Roynecro97/pyheaders.git
   ```

3. Build the plugins:

   ```sh
   cd pyheaders
   ./update-plugin.sh
   ```

4. Install _pyheaders_:

   From the _pyheaders_ directory run:

   ```sh
   python setup.py install
   ```

   Or to install in develop mode:

   ```sh
   python setup.py develop
   ```

5. You can now safely erase the git clone (unless _pyheaders_ is installed in develop mode).

## Using the Provided Module

_pyheaders_ can be imported and used as a module.

It provides 3 main functions: `load_path`, `load` and `loads`.

### Using the Provided Functions

Both `load` and `loads` behave similarly to the similarly named functions in the `json` and `pickle` modules.

**Using `load`:**

Assuming source.cpp contains the line

> ```cpp
> static constexpr int x = 100;
> ```

```python
import pyheaders

with open('source.cpp') as f:
    scope = pyheaders.load(f)

print(scope['x'])
```

_Output:_

> 100

**Using `loads`:**

```python
import pyheaders

cpp_code = '''\
namespace constants {
    inline constexpr auto greeting = "Hello World!";
}
'''

scope = pyheaders.loads(cpp_code, ['-std=c++17'])

print(scope['constants::greeting'])
```

_Output:_

> Hello World!

**Using `load_path`:**

`load_path` provides a useful alternative when working with big projects as it accepts the path to a C++ file or a directory that contains C++ source code and loads it.
Using this method allows _pyheaders_ to find your project's _compile_commands.json_ if it exists and read the compilation flags from there implicitly.

Assuming src/ contains a file with:

> ```cpp
> class MyClass {
>     // code ...
>     static constexpr int magic = 0x10;
>     // code ...
> };
> ```

```python
import pyheaders

scope = pyheaders.load_path('src/')

print(scope['MyClass::magic'])
```

_Output:_

> 16

_**NOTE:** When using `load` or `loads` pyheaders will look for a compile_commands.json file from the current working directory._

_**NOTE:** When using `load` or `loads` and when a file processed by `load_path` is missing from the compile_commands.json, but the compile commands were successfully loaded, pyheaders will attempt to find a close match in the compile commands and use flags that are common among all commands._
_This mechanism allows pyheaders to find the include path (for example) for a header file (that is not compiled on its own)._

## Using the Provided Executable

_pyheaders_ can also be used as an executable by running `python -m pyheaders` or simply `pyheaders`.

**Example usage:**

```sh
$ cat << EOF > a.cpp
namespace project
{
    static constexpr auto greeting = "Hello from pyheaders!";
}
EOF
$ pyheaders get a.cpp --const project::greeting --hide-names
'Hello from pyheaders!'
```
