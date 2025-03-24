# For python < 3.11, we need typing_extensions.Self instead of typing.Self
from typing_extensions import Self
from typing import Annotated, Any
from enum import StrEnum
from decimal import Decimal

import datetime
import pydantic


class Base(pydantic.BaseModel):
    pass


def parse_date(v: str | datetime.date) -> datetime.date:
    if isinstance(v, str):
        return datetime.datetime.strptime(v, "%Y-%m").date()
    return v


DateField = Annotated[datetime.date, pydantic.BeforeValidator(parse_date)]


class RateValue(Base):
    value: str
    date_from: Annotated[DateField, pydantic.Field(alias="from")]
    date_until: Annotated[DateField, pydantic.Field(alias="until", default=None)]

    @pydantic.model_validator(mode="after")
    @classmethod
    def validate_date_range(cls, data: Self):
        if data.date_until and data.date_until < data.date_from:
            raise ValueError("date_until must be after date_from")
        return data


def validate_rate_type(v: Any) -> str | None:
    allowed = {"str", "Decimal", "bool"}
    if v is not None and v not in allowed:
        raise ValueError(f'type must be one of {allowed}')
    return v


class RateType(StrEnum):
    STR = "str"
    DECIMAL = "Decimal"
    BOOL = "bool"


class RateItem(Base):
    name: str
    type: RateType
    history: list[RateValue]

    @pydantic.model_validator(mode="after")
    @classmethod
    def validate_no_overlap(cls, data: Self):
        for x in data.history:
            for y in data.history:
                if x is not y:
                    if (
                        y.date_from <= x.date_from
                        and (y.date_until is None or y.date_until >= x.date_from)
                    ) or (
                        y.date_from >= x.date_from
                        and (x.date_until is None or y.date_from <= x.date_until)
                    ):
                        raise ValueError("date ranges overlap")
        return data


def check_for_duplicates(items):
    data = {}
    for item in items:
        if item["name"] in data:
            raise ValueError(f"found duplicate name \"{item['name']}\" in list")
        data[item["name"]] = item
    return data

RateItemDict = Annotated[
    dict[str, RateItem],
    pydantic.BeforeValidator(check_for_duplicates),
]


class Rates(pydantic.RootModel):
    root: RateItemDict

    def __getitem__(self, item):
        return self.root[item]

    def _get_rate_item(self, name: str, queried_date: datetime.date | str):
        d = parse_date(queried_date)
        for item in self.root[name].history:
            if item.date_from <= d <= (item.date_until or d):
                return item

        raise ValueError(f"No value for {name} for {queried_date}.")

    def get_value_at(self, name: str, queried_date: datetime.date | str, datatype: type):
        rate_item_obj = self.root.get(name)
        rate_value = self._get_rate_item(name, queried_date)
        expected_type = {"str": str, "bool": bool, "Decimal": Decimal}.get(
            rate_item_obj.type if isinstance(rate_item_obj.type, str) else rate_item_obj.type.value
        )
        if datatype != expected_type:
            raise TypeError(f'Rate {name} expects datatype {expected_type.__name__},'
                            f'but got {datatype.__name__}.')
        if expected_type is bool:
            return rate_value.value.lower() in ("true", "1")
        if expected_type is Decimal:
            return Decimal(rate_value.value)
        if expected_type is str:
            return str(rate_value.value)
        return rate_value.value
