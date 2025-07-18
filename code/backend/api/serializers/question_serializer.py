from rest_framework import serializers
from ..models import Question, QuestionResult


class QuestionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Question
        fields = '__all__'


class QuestionResultSerializer(serializers.ModelSerializer):
    question = QuestionSerializer(read_only=True)
    class Meta:
        model = QuestionResult
        fields = '__all__'
