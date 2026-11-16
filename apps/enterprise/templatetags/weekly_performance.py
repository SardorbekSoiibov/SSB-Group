from django import template
from apps.enterprise.performance_system import personal_context

register = template.Library()


@register.inclusion_tag('boshqaruv/business/_personal_performance.html', takes_context=True)
def personal_performance_panel(context):
    return personal_context(context['request'].user)
