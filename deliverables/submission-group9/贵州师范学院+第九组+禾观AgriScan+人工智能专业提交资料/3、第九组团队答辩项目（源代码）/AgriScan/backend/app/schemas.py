import re
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, field_validator, model_validator

from .inference import SUPPORTED_CROPS

def validate_crop(value):
    if value not in SUPPORTED_CROPS:
        raise ValueError("请选择支持的作物类型。")
    return value


CropName = Annotated[str, AfterValidator(validate_crop)]


def validate_username(value):
    """Keep login identifiers exact while accepting both legacy names and emails."""
    message = "用户名需为 3–80 位字母、数字、下划线、短横线，或有效邮箱地址。"
    if not 3 <= len(value) <= 80:
        raise ValueError(message)
    if re.fullmatch(r"[a-zA-Z0-9_-]+", value):
        return value
    if value.count("@") != 1:
        raise ValueError(message)
    local, domain = value.split("@")
    labels = domain.split(".")
    if (not 1 <= len(local) <= 64 or local.startswith(".") or local.endswith(".")
            or ".." in local or not re.fullmatch(r"[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+", local)
            or len(labels) < 2
            or any(not 1 <= len(label) <= 63 or not re.fullmatch(
                r"[a-zA-Z0-9](?:[a-zA-Z0-9-]*[a-zA-Z0-9])?", label) for label in labels)):
        raise ValueError(message)
    return value


Username = Annotated[str, AfterValidator(validate_username)]


class LoginBody(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=256)


class PlotCoordinates(BaseModel):
    latitude: float | None = Field(default=None, ge=-90, le=90, allow_inf_nan=False)
    longitude: float | None = Field(default=None, ge=-180, le=180, allow_inf_nan=False)

    @model_validator(mode="after")
    def coordinates_are_paired(self):
        if (("latitude" in self.model_fields_set) != ("longitude" in self.model_fields_set)
                or (self.latitude is None) != (self.longitude is None)):
            raise ValueError("请同时填写经度和纬度，或同时清除坐标。")
        return self


class PlotCreate(PlotCoordinates):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    name: str = Field(min_length=1, max_length=100)
    crop: CropName
    area: float = Field(gt=0, le=1_000_000, allow_inf_nan=False)
    location: str = Field(default="", max_length=200)
    manager: str = Field(default="", max_length=80)


class PlotUpdate(PlotCoordinates):
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
