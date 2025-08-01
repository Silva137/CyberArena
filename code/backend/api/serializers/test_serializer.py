from rest_framework import serializers
from ..models import Test, Dataset, LLMModel
from ..serializers.dataset_serializer import DatasetSerializer
from ..serializers.llm_serializer import LLMModelSerializer
from ..serializers.question_serializer import QuestionResultSerializer
from ..serializers.user_serializer import UserSerializer


class TestSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    dataset = DatasetSerializer(read_only=True)
    llm_model = LLMModelSerializer(read_only=True)
    results = QuestionResultSerializer(many=True, read_only=True)

    class Meta:
        model = Test
        fields = '__all__'


class TestListSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    dataset = DatasetSerializer(read_only=True)
    llm_model = LLMModelSerializer(read_only=True)

    class Meta:
        model = Test
        fields = ["id", "user", "dataset", "llm_model", "correct_answers", "accuracy_percentage", "answer_distribution",
                  "completed_at", "started_at", "confidence_interval_low", "confidence_interval_high"]


class TestCreationSerializer(serializers.ModelSerializer):
    dataset_name = serializers.CharField(write_only=True, required=True)
    llm_model_name = serializers.CharField(write_only=True, required=True)

    class Meta:
        model = Test
        fields = ["id", "dataset_name", "llm_model_name"]

    def validate(self, attrs):

        dataset_name = attrs.get("dataset_name")
        llm_model_name = attrs.get("llm_model_name")

        if not Dataset.objects.filter(name=dataset_name).exists():
            raise serializers.ValidationError({"dataset_name": "Dataset not found."})

        if not LLMModel.objects.filter(name=llm_model_name).exists():
            raise serializers.ValidationError({"llm_model_name": "LLM Model not found."})

        return attrs

    def create(self, validated_data):

        dataset_name = validated_data.get("dataset_name")
        llm_model_name = validated_data.get("llm_model_name")

        dataset = Dataset.objects.get(name=dataset_name)
        llm_model = LLMModel.objects.get(name=llm_model_name)
        request = self.context.get("request")

        return Test.objects.create(
            user=request.user,
            dataset=dataset,
            llm_model=llm_model
        )
