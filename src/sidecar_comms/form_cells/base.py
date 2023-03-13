"""
Form Cells are our "better" version of widgets. On the frontend, they look like widgets but
live in the cell input as opposed to being a cell output. When a cell is switched to "form",
a cell metadata delta is pushed to the sidecar and sidecar sends the info on to the kernel
over Comm.

These models here represent different types of frontend form cells. A Datetime object in
this file represents a date time picker form cell widget on the frontend.

The backend form cell objects have their state updated when frontend changes (user slides
a slider or fills out a text input) through the same delta to sidecar -> sidecar comm to kernel
flow as when a cell is first switched to "form".

A user can programmatically create a form cell, such as typing model = Datetime() and outputting
model in a cell. In that case, instead of ipython repr'ing the model, we get into the ipython
display override and send a comm message to the sidecar to change the cell to "form".

A user can also programmatically update the state of a form cell, and thanks to the ObservableModel
pattern, those changes will be sent over Comm to the sidecar which will create cell metadata deltas
that update the frontend state.

Finally, the backend implementation of form cells use a discriminator pattern. You can create a
form cell from a dictionary that is coming in from the frontend. Example:

model = pydantic.parse_obj_as(FormCell, {"input_type": "datetime", "value": "2021-01-01"})
model
>>> Datetime(value=datetime.datetime(2021, 1, 1, 0, 0, tzinfo=datetime.timezone.utc))
"""
import enum
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional, Union

from IPython.core.interactiveshell import InteractiveShell
from pydantic import Extra, Field, PrivateAttr, parse_obj_as, validator
from typing_extensions import Annotated

from sidecar_comms.form_cells.observable import Change, ObservableModel
from sidecar_comms.handlers.variable_explorer import set_kernel_variable
from sidecar_comms.outbound import SidecarComm, comm_manager

FORM_CELL_CACHE: Dict[str, "FormCellBase"] = {}


class ExecutionTriggerBehavior(str, enum.Enum):
    change_variable_only = "change_variable_only"
    change_variable_and_execute_all_below = "change_variable_and_execute_all_below"
    change_variable_and_execute_all = "change_variable_and_execute_all"


class FormCellBase(ObservableModel):
    """
    Base class for form cells.
     - registers the class instance to the FORM_CELL_CACHE
     - makes sure comm is open between sidecar and kernel
     - when repr'd, override the ipython display handler and instead send a comm message so
       that the sidecar can handle `display_form_cell`

    Should not be used directly, but instead used as a base class for other form cell
    models declared below.
    """

    _comm: SidecarComm = PrivateAttr()
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    label: str = ""
    model_variable_name: str = ""
    value_variable_name: str = ""
    variable_type: str = ""
    value: Any = None
    settings: ObservableModel = None
    execution_trigger_behavior: ExecutionTriggerBehavior = (
        ExecutionTriggerBehavior.change_variable_only
    )
    input_type: str = ""

    # only used for tests
    _ipy: Optional[InteractiveShell] = PrivateAttr()

    def __init__(self, **data):
        super().__init__(**data)
        self._comm = comm_manager().open_comm("form_cells")
        FORM_CELL_CACHE[self.id] = self

        self.observe(self._sync_sidecar)
        self.observe(self._on_value_update, names=["value"])
        self.settings.observe(self._sync_sidecar)

        # make sure the value variable is available on init
        self.value_variable_name = (
            data.get("value_variable_name") or f"{self.model_variable_name}_value"
        )
        set_kernel_variable(self.value_variable_name, self.value)

    def __repr__(self):
        props = ", ".join(f"{k}={v!r}" for k, v in self.dict(exclude={"id"}).items())
        return f"<{self.__class__.__name__} {props}>"

    def _sync_sidecar(self, change: Change):
        """Send a comm_msg to the sidecar to update the form cell metadata."""
        # not sending `change` through because we're doing a full replace
        # based on the latest state of the model
        data = self.dict()

        if self.input_type == "datetime":
            # specifically convert from datetime to YYYY-mm-ddTHH:MM,
            # otherwise the frontend will have issues rendering
            data["value"] = self.value.strftime("%Y-%m-%dT%H:%M")

        self._comm.send(handler="update_form_cell", body=data)

    def _on_value_update(self, change: Change) -> None:
        """Update the kernel variable when the .value changes
        based on the associated .value_variable_name.
        """
        set_kernel_variable(self.value_variable_name, change.new)

    def _ipython_display_(self):
        """Send a message to the sidecar and print the form cell repr."""
        self._comm.send(handler="display_form_cell", body=self.dict())
        print(self.__repr__())

    def update(self, data: dict) -> None:
        """Set attributes on a form cell from a dict of values.

        NOTE: for any deep merging beyond or deeper than `settings`, we will
        need to revisit/rethink this. For now, we only get top-level changes
        and `settings` changes that are one level deep."""
        for name, value in data.items():
            if name == "settings":
                for setting_name, setting_value in value.items():
                    setattr(self.settings, setting_name, setting_value)
                continue
            setattr(self, name, value)


# --- Specific models ---
def validate_datetime_value(value):
    """Make sure value is a valid datetime object"""
    if isinstance(value, str):
        if value.endswith("Z"):
            value = value.replace("Z", "+00:00")
        value = datetime.fromisoformat(value)
    return value


class Datetime(FormCellBase):
    input_type: Literal["datetime"] = "datetime"
    value: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    _validate_value = validator("value", pre=True, always=True)(validate_datetime_value)


class SliderSettings(ObservableModel):
    min: Union[int, float] = 0
    max: Union[int, float] = 10
    step: Union[int, float] = Field(default=1, gt=0)


class Slider(FormCellBase):
    input_type: Literal["slider"] = "slider"
    value: Union[int, float] = 0
    settings: SliderSettings = Field(default_factory=SliderSettings)


class OptionsSettings(ObservableModel):
    options: List[str] = Field(default_factory=list)

    @validator("options", pre=True, always=True)
    def validate_options(cls, value):
        """Make sure values are a unique list of strings."""
        if not isinstance(value, list):
            value = [value]
        return value


class Dropdown(FormCellBase):
    input_type: Literal["dropdown"] = "dropdown"
    value: str = ""
    variable_type: Union[str, dict] = ""
    settings: OptionsSettings = Field(default_factory=OptionsSettings)


class Checkboxes(FormCellBase):
    input_type: Literal["checkboxes"] = "checkboxes"
    value: List[str] = Field(default_factory=list)
    variable_type: Union[str, dict] = ""
    settings: OptionsSettings = Field(default_factory=OptionsSettings)


class TextSettings(ObservableModel):
    min_length: int = 0
    max_length: int = 1000


class Text(FormCellBase):
    input_type: Literal["text"] = "text"
    value: str = ""
    settings: TextSettings = Field(default_factory=TextSettings)


class CustomSettings(ObservableModel, extra=Extra.allow):
    pass


class Custom(FormCellBase, extra=Extra.allow):
    input_type: Literal["custom"] = "custom"
    settings: CustomSettings = Field(default_factory=CustomSettings)

    def __repr__(self):
        return self.model_variable_name.title() + super().__repr__()


# FormCell is just a type, you can't instantiate FormCell()
# See top of file / module docstring for example usage with pydantic.parse_obj_as
model_union = Union[
    Checkboxes,
    Datetime,
    Dropdown,
    # Multiselect,
    Slider,
    Text,
    Custom,
]
FormCell = Annotated[model_union, Field(discriminator="input_type")]
# we don't have any other way to check whether an `input_type` value is valid
valid_model_input_types = [m.__fields__["input_type"].default for m in model_union.__args__]


def parse_as_form_cell(data: dict) -> FormCell:
    # check if the input_type is valid before parsing into a model
    # in case we need to overwrite it as "custom"
    if data["input_type"] not in valid_model_input_types:
        data["input_type"] = "custom"
    return parse_obj_as(FormCell, data)
