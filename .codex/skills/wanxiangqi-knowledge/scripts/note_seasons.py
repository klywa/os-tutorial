SEASONS = ('S1', 'S2')


def normalize(values):
    if not isinstance(values, list) or not values or any(v not in SEASONS for v in values):
        raise ValueError('请选择至少一个有效的适用赛季')
    return [season for season in SEASONS if season in values]


def membership(note):
    return note.get('seasons', ['S1'])
