from decimal import Decimal

import pytest
import pydantic
import requests_mock

from nerc_rates import load_from_url, rates, models


def test_load_from_url():
    mock_response_text = """
    - name: CPU SU Rate
      type: str
      history:
        - value: "0.013"
          from: 2023-06
    """
    with requests_mock.Mocker() as m:
        m.get(rates.DEFAULT_RATES_URL, text=mock_response_text)
        r = load_from_url()
        assert r.get_value_at("CPU SU Rate", "2023-06", str) == "0.013"


def test_invalid_date_order():
    rate = {"value": "1", "from": "2020-04", "until": "2020-03"}
    with pytest.raises(
        pydantic.ValidationError, match="date_until must be after date_from"
    ):
        models.RateValue.model_validate(rate)


def test_invalid_rate_type():
    rate = {"name": "Test Rate", "type": "invalid_type",
            "history": [
            {"value": "1", "from": "2020-01"},
        ],
    }
    with pytest.raises(
        pydantic.ValidationError, match="Input should be 'str', 'Decimal' or 'bool'"
    ):
        models.RateItem.model_validate(rate)


def test_missing_type_field():
    rate = {
        "name": "Test Rate Missing Type",
        "history": [
            {"value": "1.23", "from": "2023-01"},
        ],
    }
    with pytest.raises(
        pydantic.ValidationError, match="type\n  Field required"
    ):
        models.RateItem.model_validate(rate)


@pytest.mark.parametrize(
    "rate",
    [
        # Two values with no end date
        {
            "name": "Test Rate",
            "type": "Decimal",
            "history": [
                {"value": "1", "from": "2020-01"},
                {"value": "2", "from": "2020-03"},
            ],
        },
        # Second value overlaps first value at end
        {
            "name": "Test Rate",
            "type": "Decimal",
            "history": [
                {"value": "1", "from": "2020-01", "until": "2020-04"},
                {"value": "2", "from": "2020-03"},
            ],
        },
        # Second value overlaps first value at start
        {
            "name": "Test Rate",
            "type": "Decimal",
            "history": [
                {"value": "1", "from": "2020-04", "until": "2020-06"},
                {"value": "2", "from": "2020-03", "until": "2020-05"},
            ],
        },
        # Second value is contained by first value
        {
            "name": "Test Rate",
            "type": "Decimal",
            "history": [
                {"value": "1", "from": "2020-01", "until": "2020-06"},
                {"value": "2", "from": "2020-03", "until": "2020-05"},
            ],
        },
    ],
)
def test_invalid_date_overlap(rate):
    with pytest.raises(pydantic.ValidationError, match="date ranges overlap"):
        models.RateItem.model_validate(rate)


@pytest.mark.parametrize(
    "rate_item_data",
    [
        {
            "name": "Invalid Bool",
            "type": "bool",
            "history": [
                {"value": "yes", "from": "2023-01"},
            ],
        },
        {
            "name": "Invalid Decimal",
            "type": "Decimal",
            "history": [
                {"value": "not_a_decimal", "from": "2023-01"},
            ],
        },
    ],
)
def test_invalid_rate_type(rate_item_data):
    with pytest.raises(pydantic.ValidationError, match="Bool field must be a string of either True or False|is not valid Decimal"):
        models.RateItem.model_validate(rate_item_data)


def test_rates_get_value_at():
    r = rates.Rates(
        [
            {
                "name": "Test Rate",
                "type": "str",
                "history": [
                    {"value": "1", "from": "2020-01", "until": "2020-12"},
                    {"value": "2", "from": "2021-01"},
                ],
            }
        ]
    )
    assert r.get_value_at("Test Rate", "2020-01", str) == "1"
    assert r.get_value_at("Test Rate", "2020-12", str) == "1"
    assert r.get_value_at("Test Rate", "2021-01", str) == "2"
    with pytest.raises(ValueError):
        assert r.get_value_at("Test Rate", "2019-01", str)


def test_fail_with_duplicate_names():
    with pytest.raises(
        pydantic.ValidationError, match=r"found duplicate name .* in list"
    ):
        rates.Rates(
            [
                {
                    "name": "Test Rate",
                    "type": "Decimal",
                    "history": [
                        {"value": "1", "from": "2020-01", "until": "2020-12"},
                        {"value": "2", "from": "2021-01"},
                    ],
                },
                {
                    "name": "Test Rate",
                    "type": "Decimal",
                    "history": [
                        {"value": "1", "from": "2020-01", "until": "2020-12"},
                        {"value": "2", "from": "2021-01"},
                    ],
                },
            ]
        )


@pytest.fixture
def sample_rates():
    return rates.Rates(
        [
            # Decimal-typed RateItem
            {
                "name": "Decimal Rate",
                "type": "Decimal",
                "history": [{"value": "1.23", "from": "2020-01"}],
            },
            # Boolean-typed RateItem
            {
                "name": "Boolean Rate",
                "type": "bool",
                "history": [{"value": "true", "from": "2020-01"}],
            },
            # String-typed RateItem
            {
                "name": "String Rate",
                "type": "str",
                "history": [{"value": "standard", "from": "2020-01"}],
            },
        ]
    )


@pytest.mark.parametrize(
    "name, query_date, datatype, expected, raises",
    [
        ("Decimal Rate", "2020-01", Decimal, Decimal("1.23"), None),
        ("Boolean Rate", "2020-01", bool, True, None),
        ("String Rate", "2020-01", str, "standard", None),
        ("Decimal Rate", "2020-01", None, Decimal("1.23"), None),
        ("Boolean Rate", "2020-01", None, True, None),
        ("String Rate", "2020-01", None, "standard", None),
        ("Decimal Rate", "2020-01", bool, None, TypeError),
        ("Boolean Rate", "2020-01", Decimal, None, TypeError),
    ],
)


def test_get_value_at_cases(sample_rates, name, query_date, datatype, expected, raises):
    if raises:
        with pytest.raises(raises):
            sample_rates.get_value_at(name, query_date, datatype)
    else:
        result = sample_rates.get_value_at(name, query_date, datatype)
        assert result == expected
