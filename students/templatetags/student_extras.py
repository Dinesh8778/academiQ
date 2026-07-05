from django import template

register = template.Library()


@register.filter
def get_item(dictionary, key):
    """Usage: {{ my_dict|get_item:some_key }}"""
    if dictionary is None:
        return None
    return dictionary.get(key)
