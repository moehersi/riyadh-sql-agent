import pytest

from agent import is_safe, run_sql


def test_allows_select_and_with():
    assert is_safe("SELECT 1")
    assert is_safe("with x as (select 1) select * from x;")


@pytest.mark.parametrize("sql", ["DELETE FROM orders", "DROP TABLE customers", "SELECT 1; DELETE FROM orders", "UPDATE orders SET is_late=0"])
def test_blocks_writes(sql):
    assert not is_safe(sql)
    with pytest.raises(ValueError):
        run_sql(sql)


def test_reads_data():
    assert run_sql("SELECT COUNT(*) FROM customers") == [(300,)]
