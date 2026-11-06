from pydantic import BaseModel, ConfigDict

# Longest stable key a client may supply, such as a graph node or edge key.
MAX_KEY_LENGTH = 128


class StrictBaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
