from pathlib import Path

import pandas as pd
import pytest

from src import special_format_parser as sfp


def test_is_metadata_summary_and_data_line():
    assert sfp.is_metadata_line('')
    assert sfp.is_metadata_line('计算坐标系:X向后、Y向右')
    assert not sfp.is_metadata_line('BODY')

    assert sfp.is_summary_line('CLa Cdmin CmCL')
    assert not sfp.is_summary_line('1.0 2.0 3.0')

    assert sfp.is_data_line('0.00 1.23 4.56')
    assert not sfp.is_data_line('Alpha CL CD')


def test_is_part_name_line_with_next_header():
    line = 'BODY'
    next_line = 'Alpha CL CD Cm Cx Cy Cz'
    assert sfp.is_part_name_line(line, next_line)

    # single short line without header still qualifies
    assert sfp.is_part_name_line('WING')


def test_get_part_names_and_parse(tmp_path: Path):
    content = '\n'.join([
        '计算坐标系:X向后',
        '',
        'quanji',
        'Alpha CL CD Cm Cx Cy Cz',
        '-2.00 -0.10625 0.03809 0.00626 0.03059 -0.01136 0.01894',
        '0.00 0.00652 0.03443 -0.02196 0.02898 -0.01158 -0.00198',
        'CLa Cdmin CmCL',
        '',
        'BODY',
        'Alpha CL CD Cm Cx Cy Cz',
        '-2.00 -0.03869 0.02362 -0.00061 0.02961 -0.01279 0.00106',
    ])

    p = tmp_path / 'sample.mtfmt'
    p.write_text(content, encoding='utf-8')

    parts = sfp.get_part_names(p)
    assert 'quanji' in parts and 'BODY' in parts

    parsed = sfp.parse_special_format_file(p)
    assert 'quanji' in parsed and 'BODY' in parsed
    df_q = parsed['quanji']
    assert isinstance(df_q, pd.DataFrame)
    # numeric conversion: ensure columns are numeric or at least convertible
    assert df_q.shape[0] == 2


def test_looks_like_special_format_by_extension(tmp_path: Path):
    p = tmp_path / 'x.mtfmt'
    p.write_text('dummy', encoding='utf-8')
    assert sfp.looks_like_special_format(p)


def test_parse_skips_mismatched_rows_and_summary(tmp_path: Path):
    # header has 4 cols but a data row only has 3 -> should be skipped
    lines = [
        'PARTA',
        'Alpha CL CD Cm',
        '1.0 2.0 3.0 4.0',
        '2.0 3.0 4.0',  # mismatched
        'CLa Cdmin',
    ]
    p = tmp_path / 'mismatch.mtfmt'
    p.write_text('\n'.join(lines), encoding='utf-8')
    parsed = sfp.parse_special_format_file(p)
    assert 'PARTA' in parsed
    assert parsed['PARTA'].shape[0] == 1
