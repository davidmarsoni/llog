from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.middleware.csrf import get_token
from django.contrib.auth.decorators import login_required
import json

def set_csrf_token(request):
    """
    This view sets the CSRF cookie
    """
    token = get_token(request)
    return JsonResponse({'csrf_token': token})

@require_http_methods(["POST"])
def login_view(request):
    data = json.loads(request.body)
    username = data.get('username')
    password = data.get('password')
    
    user = authenticate(request, username=username, password=password)
    if user is not None:
        login(request, user)
        return JsonResponse({'success': True})
    return JsonResponse({'success': False}, status=400)

@require_http_methods(["POST"])
def register(request):
    data = json.loads(request.body)
    username = data.get('username')
    password = data.get('password')
    email = data.get('email')
    
    # Simple validation
    if not username or not password or not email:
        return JsonResponse({'error': 'Please provide all required fields'}, status=400)
    
    try:
        user = User.objects.create_user(username=username, email=email, password=password)
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)

@login_required
def logout_view(request):
    logout(request)
    return JsonResponse({'success': True})

@login_required
def user(request):
    user = request.user
    return JsonResponse({
        'id': user.id,
        'username': user.username,
        'email': user.email,
    })

def user_list(request):
    """
    Return a list of all users
    """
    users = User.objects.all().values('id', 'username', 'email')
    return JsonResponse(list(users), safe=False)