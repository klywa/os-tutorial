"""Pure name and alias matching shared by portable import and monitoring."""


def resolve(value, parameter, catalog):
    key = parameter.get('key', '?')
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f'参数 {key} 的实体名称无效：{value!r}')
    selector = value.strip()
    categories = parameter.get('entity_categories')
    candidates = [row for row in catalog.values()
                  if not categories or row.get('category') in categories]
    matches = [row for row in candidates if isinstance(row.get('name'), str) and row['name'].strip() == selector]
    if not matches:
        matches = [row for row in candidates if isinstance(row.get('aliases'), list)
                   and any(isinstance(alias, str) and alias.strip() == selector for alias in row['aliases'])]
    if not matches:
        raise ValueError(f'参数 {key} 的实体名称未知：{value}')
    if not categories and len({row.get('category') for row in matches}) > 1:
        raise ValueError(f'参数 {key} 的实体名称跨类别重名，请指定 entity_categories：{value}')
    versions = {(row.get('category'), row['name'].strip()) for row in matches}
    matches = [row for row in candidates if isinstance(row.get('name'), str)
               and (row.get('category'), row['name'].strip()) in versions]
    return sorted(matches, key=lambda row: row['id'])
