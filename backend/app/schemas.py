from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, field_validator

from .inference import SUPPORTED_CROPS

def validate_crop(value):
    if value not in SUPPORTED_CROPS:
        raise ValueError("请选择支持的作物类型。")
    return value


CropName = Annotated[str, AfterValidator(validate_crop)]


class LoginBody(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=256)


class PlotCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    name: str = Field(min_length=1, max_length=100)
    crop: CropName
    area: float = Field(gt=0, le=1_000_000, allow_inf_nan=False)
    location: str = Field(default="", max_length=200)
    manager: str = Field(default="", max_length=80)


class PlotUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    name: str | None = Field(default=None, min_length=1, max_length=100)
    crop: CropName | None = None
    area: float | None = Field(default=None, gt=0, le=1_000_000, allow_inf_nan=False)
    location: str | None = Field(default=None, max_length=200)
    manager: str | None = Field(default=None, max_length=80)

    @field_validator("name", "crop", "area", "location", "manager")
    @classmethod
    def forbid_explicit_null(cls, value):
        if value is None:
            raise ValueError("此字段不可为空。")
        return value
