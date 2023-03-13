"""
Comm target registration and message handling for inbound messages.
(Sidecar -> kernel)
"""
import traceback

from ipykernel.comm import Comm
from IPython import get_ipython

from sidecar_comms.form_cells.base import (
    FORM_CELL_CACHE,
    parse_as_form_cell,
    validate_datetime_value,
)
from sidecar_comms.handlers.variable_explorer import (
    get_kernel_variables,
    rename_kernel_variable,
    set_kernel_variable,
)
from sidecar_comms.models import CommMessage


def inbound_comm(comm, open_msg):
    """Handles messages from the sidecar."""

    @comm.on_msg
    def _recv(msg):
        data = msg["content"]["data"]
        # echo for debugging
        echo_msg = CommMessage(body={"status": "received", "data": data})
        comm.send(echo_msg.dict())

        try:
            handle_msg(data, comm)
        except Exception as e:
            # echo back any errors in the event we can't print/log to an output
            error_msg = CommMessage(
                body={
                    "status": "error",
                    "error": f"error handling message: {e} -> {traceback.format_exc()}",
                    "msg": msg,
                }
            )
            comm.send(error_msg.dict())

    comm.send({"status": "connected", "source": "sidecar_comms"})


def handle_msg(data: dict, comm: Comm) -> None:
    """Checks the message type and calls the appropriate handler."""
    inbound_msg = data.pop("msg", None)

    # TODO: pydantic discriminators for message types->handlers
    if inbound_msg == "get_kernel_variables":
        variables = get_kernel_variables()
        msg = CommMessage(
            body=variables,
            handler="get_kernel_variables",
        )
        comm.send(msg.dict())

    if inbound_msg == "rename_kernel_variable":
        if "old_name" in data and "new_name" in data:
            status = rename_kernel_variable(data["old_name"], data["new_name"])
            msg = CommMessage(
                body={"status": status},
                handler="rename_kernel_variable",
            )
            comm.send(msg.dict())

    if inbound_msg == "update_form_cell":
        form_cell_id = data.pop("form_cell_id")
        form_cell = FORM_CELL_CACHE[form_cell_id]

        if data["input_type"] == "datetime":
            # specifically convert back to datetime object;
            # otherwise the value variable will remain a string
            data["value"] = validate_datetime_value(data["value"])

        form_cell.update(data)
        msg = CommMessage(
            body=form_cell.dict(),
            handler="update_form_cell",
        )
        comm.send(msg.dict())

    if inbound_msg == "create_form_cell":
        # form cell object created from the frontend
        cell_id = data.pop("cell_id")
        form_cell = parse_as_form_cell(data)
        get_ipython().user_ns[data["model_variable_name"]] = form_cell
        # send a comm message back to the sidecar to allow it to track
        # the cell id to form cell id mapping by echoing the provided cell_id
        # and also including the newly-generated form cell model that includes
        # the form cell id (uuid) and any other default properties
        msg = CommMessage(
            body={"cell_id": cell_id, **form_cell.dict()},
            handler="register_form_cell",
        )
        comm.send(msg.dict())

    if inbound_msg == "assign_value_variable":
        form_cell_id = data["form_cell_id"]
        form_cell = FORM_CELL_CACHE[form_cell_id]
        set_kernel_variable(data["value_variable_name"], form_cell.value)
