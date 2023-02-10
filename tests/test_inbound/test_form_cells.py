from IPython.core.interactiveshell import InteractiveShell

from sidecar_comms.form_cells.base import (
    Checkboxes,
    Custom,
    Datetime,
    Dropdown,
    Slider,
    Text,
    parse_as_form_cell,
    update_form_cell,
)


class TestParseFormCell:
    def test_parse_checkboxes(self, get_ipython: InteractiveShell):
        data = {
            "input_type": "checkboxes",
            "model_variable_name": "test",
            "value": ["test"],
            "variable_type": "str",
            "settings": {
                "options": ["test"],
            },
            "ipython_shell": get_ipython,
        }
        form_cell = parse_as_form_cell(data)
        assert form_cell.input_type == "checkboxes"
        assert form_cell.model_variable_name == "test"
        assert form_cell.value == ["test"]
        assert form_cell.variable_type == "str"
        assert form_cell.settings.options == ["test"]
        assert isinstance(form_cell, Checkboxes)

    def test_parse_datetime(self, get_ipython: InteractiveShell):
        data = {
            "input_type": "datetime",
            "model_variable_name": "test",
            "value": "2023-01-01T00:00:00Z",
            "variable_type": "datetime",
            "settings": {},
            "ipython_shell": get_ipython,
        }
        form_cell = parse_as_form_cell(data)
        assert form_cell.input_type == "datetime"
        assert form_cell.model_variable_name == "test"
        assert form_cell.value == "2023-01-01T00:00"
        assert form_cell.variable_type == "datetime"
        assert form_cell.settings == {}
        assert isinstance(form_cell, Datetime)

    def test_parse_dropdown(self, get_ipython: InteractiveShell):
        data = {
            "input_type": "dropdown",
            "model_variable_name": "test",
            "value": "a",
            "variable_type": "str",
            "settings": {
                "options": ["a", "b", "c"],
            },
            "ipython_shell": get_ipython,
        }
        form_cell = parse_as_form_cell(data)
        assert form_cell.input_type == "dropdown"
        assert form_cell.model_variable_name == "test"
        assert form_cell.value == "a"
        assert form_cell.variable_type == "str"
        assert form_cell.settings.options == ["a", "b", "c"]
        assert isinstance(form_cell, Dropdown)

    def test_parse_slider(self, get_ipython: InteractiveShell):
        data = {
            "input_type": "slider",
            "model_variable_name": "test",
            "value": 0,
            "variable_type": "int",
            "settings": {
                "min": 0,
                "max": 100,
                "step": 1,
            },
            "ipython_shell": get_ipython,
        }
        form_cell = parse_as_form_cell(data)
        assert form_cell.input_type == "slider"
        assert form_cell.model_variable_name == "test"
        assert form_cell.value == 0
        assert form_cell.variable_type == "int"
        assert form_cell.settings.min == 0
        assert form_cell.settings.max == 100
        assert form_cell.settings.step == 1
        assert isinstance(form_cell, Slider)

    def test_parse_text(self, get_ipython: InteractiveShell):
        data = {
            "input_type": "text",
            "model_variable_name": "test",
            "value": "test",
            "settings": {
                "min_length": 0,
                "max_length": 1000,
            },
            "ipython_shell": get_ipython,
        }
        form_cell = parse_as_form_cell(data)
        assert form_cell.input_type == "text"
        assert form_cell.model_variable_name == "test"
        assert form_cell.value == "test"
        assert form_cell.settings.min_length == 0
        assert form_cell.settings.max_length == 1000
        assert isinstance(form_cell, Text)

    def test_parse_custom(self, get_ipython: InteractiveShell):
        data = {
            "input_type": "my_new_form_cell_type",
            "model_variable_name": "test",
            "value": "test",
            "foo": "bar",
            "settings": {
                "abc": "def",
            },
            "ipython_shell": get_ipython,
        }
        form_cell = parse_as_form_cell(data)
        assert form_cell.input_type == "custom"
        assert form_cell.model_variable_name == "test"
        assert form_cell.value == "test"
        assert form_cell.foo == "bar"
        assert form_cell.settings.abc == "def"
        assert isinstance(form_cell, Custom)


class TestFormCellSetup:
    def test_value_variable_created(self, get_ipython: InteractiveShell):
        """Test that a value variable is created and available in the
        user namespace when a form cell is created."""
        data = {
            "input_type": "text",
            "model_variable_name": "test",
            "value": "test",
            "settings": {
                "min_length": 0,
                "max_length": 1000,
            },
            "ipython_shell": get_ipython,
        }
        form_cell = parse_as_form_cell(data)
        assert form_cell.value_variable_name == "test_value"
        assert "test_value" in get_ipython.user_ns

    def test_value_variable_updated(self, get_ipython: InteractiveShell):
        """Test that a value variable is updated when the form cell value
        is updated."""
        data = {
            "input_type": "text",
            "model_variable_name": "test",
            "value": "test",
            "settings": {
                "min_length": 0,
                "max_length": 1000,
            },
            "ipython_shell": get_ipython,
        }
        form_cell = parse_as_form_cell(data)
        form_cell.value = "new value"
        assert get_ipython.user_ns["test_value"] == "new value"


class TestFormCellUpdates:
    def test_update_dict_settings(self):
        """Test that updating a form cell with a nested dictionary
        updates the settings without dropping existing settings
        or altering the original model structure."""
        data = {
            "input_type": "checkboxes",
            "model_variable_name": "test",
            "value": ["a"],
            "settings": {
                "options": ["a", "b", "c"],
            },
        }
        form_cell = parse_as_form_cell(data)
        update_dict = {"settings": {"options": ["a", "b", "x", "y"]}}
        updated_form_cell = update_form_cell(form_cell, update_dict)
        assert updated_form_cell.value == ["a"]
        assert updated_form_cell.settings.options == ["a", "b", "x", "y"]

    def test_update_dict_value_settings(self):
        """Test that updating a form cell with a nested dictionary
        updates the settings without dropping existing settings
        or altering the original model structure."""
        data = {
            "input_type": "checkboxes",
            "model_variable_name": "test",
            "value": ["a"],
            "settings": {
                "options": ["a", "b", "c"],
            },
        }
        form_cell = parse_as_form_cell(data)
        update_dict = {
            "settings": {"options": ["a", "b", "x", "y"]},
            "value": ["b", "x"],
        }
        updated_form_cell = update_form_cell(form_cell, update_dict)
        assert updated_form_cell.value == ["b", "x"]
        assert updated_form_cell.settings.options == ["a", "b", "x", "y"]
