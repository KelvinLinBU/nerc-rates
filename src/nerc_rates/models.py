# For python < 3.11, we need typing_extensions.Self instead of typing.Self
from typing_extensions import Self
from typing import Annotated

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
    type: str | None = None 
    date_from: Annotated[DateField, pydantic.Field(alias="from")]
    date_until: Annotated[DateField, pydantic.Field(alias="until", default=None)]

    @pydantic.model_validator(mode="after")
    @classmethod
    def validate_date_range_type(cls, data: Self):
        if data.date_until and data.date_until < data.date_from:
            raise ValueError("date_until must be after date_from")
        if data.type and data.type not in {"str", "Decimal", "bool"}:
            raise ValueError('type must be one of "str", "Decimal", or "bool"')
        return data


class RateItem(Base):
    name: str
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
        rate_item = self.root.get(name)
        if not rate_item:
            raise ValueError(f"Rate '{name}' not found")
        for item in rate_item.history:
            if item.date_from <= d <= (item.date_until or d):
                return item
        raise ValueError(f"No value for '{name}' found for date '{queried_date}'.")
    
    def get_value_at(self, name: str, queried_date: datetime.date | str, datatype: type | None = None): 
        rate_item = self._get_rate_item(name, queried_date)
        if rate_item.type:
            expected_type = {"str": str, "bool": bool, "Decimal": Decimal}.get(rate_item.type)
            if not datatype:
                return rate_item.value
            if datatype != expected_type: 
                raise TypeError(f'Rate "{name}" expects datatype {expected_type.__name__}, 'f'but got {datatype.__name__}.')
            if expected_type == bool:
                return rate_item.value.lower() in ("true", "1")
            if expected_type == Decimal:
                return Decimal(rate_item.value)
            if expected_type == str:
                return str(rate_item.value)
        if datatype and not rate_item.type:
            raise TypeError(f'Rate "{name}" does not define a type but you provided datatype={datatype.__name__}.')
        return rate_item.value