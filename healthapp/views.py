from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from datetime import date, datetime
import json
import groq
from .models import UserProfile, DailyLog, Meal, Exercise, ChatMessage, ChatHistory
from django.conf import settings
from openai import OpenAI

import logging
logger = logging.getLogger(__name__)

def get_groq_client():
    return groq.Groq(api_key=settings.GROQ_API_KEY)

@login_required
def dashboard(request):
    # Get or create UserProfile
    try:
        user_profile = request.user.userprofile
    except UserProfile.DoesNotExist:
        # Create default profile if it doesn't exist
        user_profile = UserProfile.objects.create(
            user=request.user,
            height=170,  # Default height
            weight=70,   # Default weight
            gender='male',  # Default gender
            body_type='mesomorph',
            activity_level='moderate',
            fitness_goal='maintenance'
        )
        return redirect('profile')  # Redirect to profile to complete setup
    
    today = date.today()
    
    # Get or create daily log
    daily_log, created = DailyLog.objects.get_or_create(
        user=request.user,
        date=today,
        defaults={'weight': user_profile.weight}
    )
    
    # Get today's data
    meals = Meal.objects.filter(user=request.user, date=today).order_by('time')
    exercises = Exercise.objects.filter(user=request.user, date=today)
    
    # If no exercises for today, create a default workout based on fitness goal
    if not exercises.exists():
        create_default_workout(request.user, today, user_profile.fitness_goal)
        # Fetch the newly created exercises
        exercises = Exercise.objects.filter(user=request.user, date=today)
    
    # Calculate percentages safely
    def safe_percentage(value, target):
        return min(int((value / target) * 100) if target > 0 else 0, 100)
    
    protein_target = user_profile.weight * 1.6  # 1.6g protein per kg of body weight
    
    context = {
        'user_profile': user_profile,
        'daily_goals': {
            'calories_target': int(user_profile.daily_calorie_needs),
            'calories_consumed': daily_log.calories_consumed,
            'calories_percentage': safe_percentage(daily_log.calories_consumed, user_profile.daily_calorie_needs),
            'water_target': 3.0,
            'water_consumed': daily_log.water_consumed,
            'water_percentage': safe_percentage(daily_log.water_consumed, 3.0),
            'protein_target': int(protein_target),
            'protein_consumed': daily_log.protein_consumed,
            'protein_percentage': safe_percentage(daily_log.protein_consumed, protein_target),
        },
        'meals': meals,
        'workout_plan': exercises,
    }
    
    return render(request, 'dashboard.html', context)

def create_default_workout(user, today, fitness_goal):
    """Create a default workout based on the user's fitness goal"""
    if fitness_goal == 'weight_loss':
        exercises = [
            {'name': 'Jumping Jacks', 'sets': 3, 'reps': 30, 'duration': 10},
            {'name': 'Push-ups', 'sets': 3, 'reps': 15},
            {'name': 'Bodyweight Squats', 'sets': 3, 'reps': 20},
            {'name': 'Mountain Climbers', 'sets': 3, 'reps': 20, 'duration': 5},
            {'name': 'Plank', 'sets': 3, 'reps': 1, 'duration': 30}
        ]
    elif fitness_goal == 'muscle_gain':
        exercises = [
            {'name': 'Push-ups', 'sets': 4, 'reps': 12},
            {'name': 'Pull-ups', 'sets': 4, 'reps': 8},
            {'name': 'Squats', 'sets': 4, 'reps': 15, 'weight': 20},
            {'name': 'Lunges', 'sets': 3, 'reps': 10, 'weight': 10},
            {'name': 'Dumbbell Rows', 'sets': 3, 'reps': 12, 'weight': 15}
        ]
    else:  # Maintenance or endurance
        exercises = [
            {'name': 'Jumping Jacks', 'sets': 2, 'reps': 30, 'duration': 5},
            {'name': 'Push-ups', 'sets': 2, 'reps': 15},
            {'name': 'Bodyweight Squats', 'sets': 2, 'reps': 15},
            {'name': 'Plank', 'sets': 2, 'reps': 1, 'duration': 30},
            {'name': 'Jogging', 'sets': 1, 'reps': 1, 'duration': 20}
        ]
    
    # Create the exercises
    for exercise_data in exercises:
        Exercise.objects.create(
            user=user,
            date=today,
            **exercise_data
        )

@login_required
def add_meal(request):
    if request.method == 'POST':
        try:
            name = request.POST.get('name')
            meal_type = request.POST.get('meal_type')
            calories = int(request.POST.get('calories'))
            protein = float(request.POST.get('protein'))
            carbs = float(request.POST.get('carbs'))
            fats = float(request.POST.get('fats'))
            time_str = request.POST.get('time')
            tags_json = request.POST.get('tags', '[]')
            
            # Convert time string to time object
            time_obj = datetime.strptime(time_str, '%H:%M').time()
            
            # Parse tags from JSON
            try:
                tags = json.loads(tags_json)
            except json.JSONDecodeError:
                tags = []
            
            # Create meal
            meal = Meal.objects.create(
                user=request.user,
                name=name,
                meal_type=meal_type,
                calories=calories,
                protein=protein,
                carbs=carbs,
                fats=fats,
                date=date.today(),
                time=time_obj,
                tags=tags
            )
            
            # Update daily log
            daily_log, created = DailyLog.objects.get_or_create(
                user=request.user,
                date=date.today()
            )
            daily_log.calories_consumed += calories
            daily_log.protein_consumed += protein
            daily_log.save()
            
            return JsonResponse({'status': 'success', 'message': 'Meal added successfully'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)})
    
    return JsonResponse({'status': 'error', 'message': 'Invalid request method'})

@login_required
def complete_exercise(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            exercise_id = data.get('exercise_id')
            
            exercise = Exercise.objects.get(id=exercise_id, user=request.user)
            exercise.completed = True
            exercise.save()
            
            return JsonResponse({'status': 'success'})
        except Exercise.DoesNotExist:
            return JsonResponse({'status': 'error', 'message': 'Exercise not found'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)})
    
    return JsonResponse({'status': 'error', 'message': 'Invalid request method'})

@login_required
def profile(request):
    # Get or create UserProfile
    user_profile, created = UserProfile.objects.get_or_create(
        user=request.user,
        defaults={
            'height': 170,
            'weight': 70,
            'body_type': 'mesomorph',
            'activity_level': 'moderate',
            'fitness_goal': 'maintenance',
            'dietary_preferences': [],
            'health_conditions': ''
        }
    )
    
    if request.method == 'POST':
        # Update user profile
        user_profile.height = float(request.POST.get('height'))
        user_profile.weight = float(request.POST.get('weight'))
        user_profile.body_type = request.POST.get('body_type')
        user_profile.activity_level = request.POST.get('activity_level')
        user_profile.fitness_goal = request.POST.get('fitness_goal')
        user_profile.dietary_preferences = request.POST.getlist('dietary_preferences')
        user_profile.health_conditions = request.POST.get('health_conditions')
        user_profile.save()
        
        return redirect('dashboard')
    
    return render(request, 'profile.html', {'user_profile': user_profile})

@login_required
def chat(request):
    try:
        profile = request.user.userprofile
    except UserProfile.DoesNotExist:
        profile = UserProfile.objects.create(
            user=request.user,
            height=170,
            weight=70,
            body_type='mesomorph',
            activity_level='moderate',
            fitness_goal='maintenance'
        )
        return redirect('profile')

    if request.method == 'POST':
        message = request.POST.get('message')
        if message:
            try:
                # Create chat history with Groq API
                client = OpenAI(
                    api_key=settings.OPENAI_API_KEY,
                    base_url=settings.OPENAI_API_BASE
                )
                
                # Prepare the system message with user's health data
                system_message = f"""You are a helpful AI assistant for a health and fitness tracking app. 
                The user's profile:
                - Height: {profile.height}cm
                - Weight: {profile.weight}kg
                - Body Type: {profile.body_type}
                - Activity Level: {profile.activity_level}
                - Fitness Goal: {profile.fitness_goal}
                - BMI: {profile.bmi:.1f}
                - BMI Category: {profile.bmi_category}
                - BMR: {profile.bmr:.0f} calories
                - Daily Calorie Needs: {profile.daily_calorie_needs:.0f} calories
                
                Provide personalized advice based on their profile. Be concise and practical.
                
                FORMAT YOUR RESPONSES:
                - Use bold headings (e.g., **Recommendation:**) for different sections
                - Use bullet points for lists of advice or tips
                - Keep paragraphs short and focused
                - Include one key takeaway at the end
                - Be encouraging and positive
                - Use markdown formatting to structure your response."""
                
                response = client.chat.completions.create(
                    model=settings.OPENAI_MODEL,
                    messages=[
                        {"role": "system", "content": system_message},
                        {"role": "user", "content": message}
                    ],
                    temperature=0.7,
                    max_tokens=500
                )
                
                ai_response = response.choices[0].message.content
                
                # Save the chat history
                ChatHistory.objects.create(
                    user=request.user,
                    message=message,
                    response=ai_response
                )
                
                return JsonResponse({
                    'status': 'success',
                    'response': ai_response
                })
            except Exception as e:
                return JsonResponse({
                    'status': 'error',
                    'message': str(e)
                })
    
    # Get recent chat history
    chat_history = ChatHistory.objects.filter(user=request.user).order_by('-timestamp')[:10]
    return render(request, 'chat.html', {
        'chat_history': chat_history,
        'profile': profile
    }) 