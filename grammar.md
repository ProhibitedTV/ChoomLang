# ChoomLang DSL Grammar (v0.1)

```ebnf
line         = ws?, op, ws, target_count, (ws, kv_pair)*, ws? ;

op           = ident ;

target_count = target, [ "[", count, "]" ] ;

target       = ident ;

count        = nonzero_digit, { digit } ;

kv_pair      = key, "=", value ;

key          = ident ;

value        = quoted_string | float | int | bool | bareword ;

quoted_string = '"', { quoted_char }, '"' ;
quoted_char   = escaped_quote | escaped_backslash | not_quote ;
escaped_quote = "\\\"" ;
escaped_backslash = "\\\\" ;
not_quote     = ? any character except unescaped '"' ? ;

bool         = "true" | "false" ;
int          = ["-"], digit, { digit } ;
float        = ["-"], digit, { digit }, ".", digit, { digit } ;
bareword     = bare_char, { bare_char } ;

ident        = ident_start, { ident_char } ;
ident_start  = letter | "_" ;
ident_char   = letter | digit | "_" | "-" ;

digit        = "0" | nonzero_digit ;
nonzero_digit = "1" | "2" | "3" | "4" | "5" | "6" | "7" | "8" | "9" ;
letter       = "A".."Z" | "a".."z" ;

bare_char    = ? any non-whitespace character except '=' and '"' ? ;
ws           = " " , { " " } ;
```

Notes:
- `count` defaults to `1` when omitted.
- Parser is deterministic and unambiguous for supported value forms.
- Output serialization uses stable key ordering for `params`.
