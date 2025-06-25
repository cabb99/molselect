import pytest
from molselect.python import grammar


def test_make_token_block_basic():
    tokens = {
        'category1': {
            'foo': {'synonyms': ['bar', 'baz']},
            'qux': {'synonyms': []},
        },
        'category2': {
            'spam': {'synonyms': ['eggs']},
        },
    }
    block, names = grammar.make_token_block(tokens, prefix='tok')
    # Check that all token names appear in the block
    assert 'FOO' in block
    assert 'QUX' in block
    assert 'SPAM' in block
    # Check that synonyms are included
    assert '"bar"' in block
    assert '"baz"' in block
    assert '"eggs"' in block
    # Check alternation string
    assert 'tok_category1' in names
    assert 'tok_category2' in names


def test_compute_last_token_pattern():
    grammar_text = '''
        FOO : "foo"
        BAR : "bar"
        // comment
        BAZ : "baz"
    '''
    pattern = grammar.compute_last_token_pattern(grammar_text)
    assert pattern.startswith('/')
    assert 'foo' in pattern
    assert 'bar' in pattern
    assert 'baz' in pattern


def test_load_json(tmp_path):
    import json
    d = {'a': 1}
    p = tmp_path / 'f.json'
    p.write_text(json.dumps(d))
    out = grammar.load_json(p)
    assert out == d


def test_main_runs(monkeypatch, tmp_path):
    # Patch ConfigManager and file I/O
    class DummyCfg:
        class Dummy:
            path = tmp_path / 'template.lark'
            paths = [tmp_path / 'macros.json']
        grammar = Dummy()
        macros = Dummy()
        keywords = Dummy()
    
    (tmp_path / 'template.lark').write_text('<<MACROS>><<MACROS_NAMES>><<KEYWORDS>><<KEYWORDS_NAMES>><<LAST_TOKEN>>')
    (tmp_path / 'macros.json').write_text('{"macros": {"cat": {"foo": {"synonyms": []}}}}')
    (tmp_path / 'keywords.json').write_text('{"keywords": {"cat": {"bar": {"synonyms": []}}}}')
    DummyCfg.macros.paths = [tmp_path / 'macros.json']
    DummyCfg.keywords.paths = [tmp_path / 'keywords.json']
    monkeypatch.setattr('molselect.python.config.ConfigManager', lambda: DummyCfg)
    grammar.main(file_out=tmp_path / 'out.lark')
    assert (tmp_path / 'out.lark').exists()
