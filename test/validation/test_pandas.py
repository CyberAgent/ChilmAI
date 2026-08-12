"""
pandas/panderaの挙動の確認
"""

import pandas as pd
import pandera as pa
import pytest
from pandas.errors import IntCastingNaNError
from pandera.errors import SchemaError, SchemaErrors


def test_pandas_int():
    """
    Intカラムのバリデーション
    """
    data = {
        "age": [24, 25, 26, 27],
    }
    df = pd.DataFrame(data)
    schema = pa.DataFrameSchema(
        columns={
            "age": pa.Column(pa.Int),
        }
    )
    try:
        schema.validate(df)
    except SchemaErrors as e:
        pytest.fail(f"validation error: {e}")


def test_pandas_float_when_include_nan():
    """
    NaNを含むと、他の値はIntなのにFloatになる
    """
    data = {"age": [1, 2, 3, None]}
    df = pd.DataFrame(data)
    schema = pa.DataFrameSchema(
        columns={
            "age": pa.Column(pa.Float, nullable=True),
        }
    )
    try:
        schema.validate(df)
    except SchemaErrors as e:
        pytest.fail(f"validation error: {e}")


def test_pandas_int_cast_error():
    """
    NaNを含むと、他の値はIntなのにFloatになる
    IntにCastするとエラーになる
    #TODO pandas>2になると、Noneを含むカラムをIntにCastしてもエラーにならないので、そのときに実装しなおす
    """
    data = {"age": [1, 2, 3, None]}
    df = pd.DataFrame(data)
    with pytest.raises(IntCastingNaNError):
        df["age"] = df["age"].astype(int)


def test_pandas_float_cast():
    """
    floatにアップキャストするのは問題ない
    """
    data = {"age": [1, 2, 3, 4]}
    df = pd.DataFrame(data)
    assert df["age"].dtype == "int64"
    df["age"] = df["age"].astype(float)
    assert df["age"].dtype == "float64"


def test_pandas_str_cast():
    """
    strを含むカラムをfloatにキャストするとエラーになる
    """
    data = {"name": ["Alice", "Bob", "Charlie", "David", None]}
    df = pd.DataFrame(data)
    assert df["name"].dtype == "object"
    with pytest.raises(ValueError):
        df["name"] = df["name"].astype(float)


def test_pandera_check_integer():
    """
    NaNを含むfloat64カラムが、NaN以外の値は整数であることをチェックする
    """

    def check_integer(series):
        return series[~series.isna()].apply(float.is_integer).all()

    schema = pa.DataFrameSchema(
        columns={
            "age": pa.Column(pa.Float, nullable=True, checks=pa.Check(check_integer)),
        }
    )
    # "3.0"のような値でも整数として扱われる
    df_1 = pd.DataFrame({"age": [1, 2, 3.0, float("nan")]})
    df_2 = pd.DataFrame({"age": [1, 2, 3, float("nan")]})
    try:
        schema.validate(df_1)
        schema.validate(df_2)
    except SchemaError as e:
        pytest.fail(f"validation error: {e}")
