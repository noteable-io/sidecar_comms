import json
import sys
from typing import Any, Optional, Union

from pydantic import BaseModel, Field

from sidecar_comms.shell import get_ipython_shell

try:
    import pandas as pd

    PANDAS_INSTALLED = True
except ImportError:
    PANDAS_INSTALLED = False

MAX_STRING_LENGTH = 1000
CONTAINER_TYPES = [list, set, frozenset, tuple]


class VariableModel(BaseModel):
    name: str
    type: str
    docstring: Optional[str]
    module: Optional[str]
    sample_value: Any  # may be the full value if small enough, only truncated for larger values
    size: Optional[Union[int, tuple]]
    size_bytes: Optional[int]
    extra: dict = Field(default_factory=dict)
    error: Optional[str]


def variable_docstring(value: Any) -> Optional[str]:
    """Returns the docstring of a variable."""
    if (doc := getattr(value, "__doc__", None)) is None:
        return
    if not isinstance(doc, str):
        return
    return doc[:5000]


def variable_type(value: Any) -> str:
    return type(value).__name__


def variable_string_repr(value: Any, max_length: Optional[int] = None) -> str:
    """Returns a string representation of a value.

    If any custom data types or configurations need to be handled,
    this is the place to do it.
    """

    if PANDAS_INSTALLED and variable_type(value) == "DataFrame":
        # if any of these are set to custom values, we need to revert them to the
        # pandas defaults, otherwise the repr may take an unnecessarily long time
        orig_max_rows = pd.get_option("display.max_rows")
        orig_max_columns = pd.get_option("display.max_columns")
        orig_max_colwidth = pd.get_option("display.max_colwidth")
        pd.set_option("display.max_rows", 20)
        pd.set_option("display.max_columns", 60)
        pd.set_option("display.max_colwidth", 50)
        string_repr = repr(value)
        pd.set_option("display.max_rows", orig_max_rows)
        pd.set_option("display.max_columns", orig_max_columns)
        pd.set_option("display.max_colwidth", orig_max_colwidth)

    else:
        string_repr = repr(value)

    return string_repr[:max_length]


def variable_shape(value: Any) -> Optional[tuple]:
    """Returns the shape (n-dimensional; rows, columns, ...) of a variable."""
    if (shape := getattr(value, "shape", None)) is None:
        return
    if not isinstance(shape, tuple):
        return
    if not shape:
        return
    if not isinstance(shape[0], int):
        return
    return shape


def variable_size(value: Any) -> Optional[Union[int, tuple]]:
    """Returns the size of a variable.

    For iterables, this returns the length / number of items.
    For matrix-like objects, this returns a tuple of the number of rows/columns, similar to .shape.
    """
    if (shape := variable_shape(value)) is not None:
        return shape

    if hasattr(value, "__len__"):
        return len(value)

    if (size := getattr(value, "size", None)) is None:
        return
    if isinstance(size, int):
        return size
    if isinstance(size, tuple):
        return size[0]


def variable_size_bytes(value: Any) -> Optional[int]:
    """Returns the size of a variable in bytes."""
    try:
        return sys.getsizeof(value)
    except Exception:
        pass
    # may be a pandas object
    # TODO: add extra pandas object handlers
    try:
        return value.memory_usage().sum()
    except Exception:
        pass


def variable_sample_value(value: Any, max_length: Optional[int] = None) -> Any:
    """Returns a short representation of a value."""
    sample_value = value
    max_length = max_length or MAX_STRING_LENGTH

    if isinstance(value, tuple(CONTAINER_TYPES)):
        sample_items = [
            variable_sample_value(item, max_length=max_length) for item in list(value)[:5]
        ]
        container_type = type(value)
        # convert back to original type if we're only showing some items
        sample_value = container_type(sample_items)

    if variable_size_bytes(value) > max_length:
        if isinstance(value, dict):
            sample_value = value.keys()
        else:
            sample_value = variable_string_repr(value, max_length) + "..."

    return sample_value


def variable_extra_properties(value: Any) -> Optional[dict]:
    """Handles extracting/generating additional properties for a variable
    based on supported types.
    """
    extra = {}

    if variable_type(value) == "DataFrame":
        extra["columns"] = list(value.columns)[:100]
        extra["index"] = list(value.index)[:100]
        extra["dtypes"] = dict(value.dtypes)

    return extra


def variable_to_model(name: str, value: Any) -> VariableModel:
    """Gathers properties of a variable to send to the sidecar through
    a variable explorer comm message.
    Should always have `name` and `type` properties; `error` will show
    conversion/inspection errors for size/size_bytes/sample_value.
    """
    basic_props = {
        "name": name,
        "docstring": variable_docstring(value),
        "type": variable_type(value),
        "module": getattr(value, "__module__", None),
    }

    # in the event we run into any parsing/validation errors,
    # we'll still send the variable model with basic properties
    # and an error message
    try:
        return VariableModel(
            sample_value=variable_sample_value(value),
            size=variable_size(value),
            size_bytes=variable_size_bytes(value),
            extra=variable_extra_properties(value),
            **basic_props,
        )
    except Exception as e:
        basic_props["error"] = f"{e!r}"

    return VariableModel(**basic_props)


def json_clean(value: Any, max_length: Optional[int] = None) -> str:
    """Ensures a value is JSON serializable, converting to a string if necessary.

    Recursively cleans values of dictionaries, and items in lists, sets, and tuples
    if necessary.
    """
    max_length = max_length or MAX_STRING_LENGTH

    if isinstance(value, dict):
        value = {k: json_clean(v) for k, v in value.items()}
    elif isinstance(value, tuple(CONTAINER_TYPES)):
        container_type = type(value)
        value = container_type([json_clean(v) for v in value])

    try:
        json.dumps(value)
        return value
    except (TypeError, ValueError):
        # either one of these may appear:
        # - TypeError: X is not JSON serializable
        # - ValueError: Can't clean for JSON: X
        return variable_string_repr(value, max_length)


def get_kernel_variables(skip_prefixes: list = None):
    """Returns a list of variables in the kernel."""
    variables = dict(get_ipython_shell().user_ns)

    skip_prefixes = skip_prefixes or [
        "_",
        "In",
        "Out",
        "get_ipython",
        "exit",
        "quit",
        "open",
    ]
    variable_data = {}
    for name, value in variables.items():
        if name.startswith(tuple(skip_prefixes)):
            continue
        variable_model = variable_to_model(name=name, value=value)
        cleaned_variable_model_dict = {k: json_clean(v) for k, v in variable_model.dict().items()}
        variable_data[name] = cleaned_variable_model_dict
    return variable_data


def rename_kernel_variable(old_name: str, new_name: str) -> str:
    """Renames a variable in the kernel."""
    ipython = get_ipython_shell()
    try:
        if new_name:
            ipython.user_ns[new_name] = ipython.user_ns[old_name]
        del ipython.user_ns[old_name]
        return "success"
    except Exception as e:
        return str(e)


def set_kernel_variable(name: str, value: Any) -> str:
    """Sets a variable in the kernel."""
    try:
        get_ipython_shell().user_ns[name] = value
        return "success"
    except Exception as e:
        return str(e)
