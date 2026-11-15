from .services import available_balance


def credit_nav_balance(request):
    if not request.user.is_authenticated:
        return {}
    return {"credit_nav_balance": available_balance(request.user)}
