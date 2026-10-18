#!/usr/bin/python3
"""Additional language choices; no repeats of the completed six-case review cohort."""
import importlib.util
from pathlib import Path
import re

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('review_language_base',HERE/'review-smoke.py')
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
base.CASES=[
 ('language-german','translate','German','Mira has 3 tasks. She has not sent the email.'),
 ('language-japanese','translate','Japanese','The meeting is not on Tuesday. It is on Wednesday at 14:30.'),
 ('language-english','translate','English',"La réunion n'est pas mardi. Elle est mercredi à 14h30.")]
original_metadata=base.metadata

def metadata():
    row=original_metadata()
    row['source_sha256'][Path(__file__).name]=base.digest(Path(__file__).resolve())
    row['test_set']='additional-language-options-v1'
    return row


def checks(case,text):
    value=text.casefold()
    if case=='language-german':
        return {'name_count_negation':all(x in value for x in ['mira','aufgaben','nicht']) and ('3' in value or 'drei' in value),
            'email_term':bool(re.search(r'e.?mail',value))}
    if case=='language-japanese':
        return {'weekday_terms':all(x in value for x in ['火曜日','水曜日']),
            'negation_term':any(x in value for x in ['ありません','ではなく','ない','なく']),
            'time_preserved':bool(re.search(r'14\s*[:時]\s*30',value))}
    return {'weekday_negation_terms':all(x in value for x in ['tuesday','wednesday','not']),
        'time_preserved':bool(re.search(r'14[:h]30|2:30\s*(?:pm|p\.m\.)',value))}


base.metadata=metadata;base.checks=checks;base.__doc__=__doc__
if __name__=='__main__':raise SystemExit(base.main())
