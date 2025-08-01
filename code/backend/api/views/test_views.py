import asyncio
from collections import Counter
import openai
import regex as re
from asgiref.sync import async_to_sync, sync_to_async
from django.db.models import F
from django.utils import timezone
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.generics import get_object_or_404
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from ..models import Test, QuestionResult, Question
from ..serializers.question_serializer import QuestionResultSerializer
from ..serializers.test_serializer import TestSerializer, TestCreationSerializer, TestListSerializer
from sklearn.metrics import classification_report
from statsmodels.stats.proportion import proportion_confint

client = openai.AsyncOpenAI(
    api_key="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",
    base_url="https://openrouter.ai/api/v1"
)

SEMAPHORE_UNITS = 30

#api_key="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", old one


class TestViewSet(viewsets.ModelViewSet):
    queryset = Test.objects.all()
    serializer_class = TestSerializer
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return TestSerializer  # single test (includes results)
        elif self.action == 'create':
            return TestCreationSerializer
        return TestListSerializer  # list of tests (without results)

    def get_queryset(self):
        queryset = Test.objects.filter(user=self.request.user)

        sort_map = {
            "accuracy_desc": "-accuracy_percentage",
            "accuracy_asc": "accuracy_percentage",
            "time_desc": "-execution_time",
            "time_asc": "execution_time",
            "id_desc": "-id",
            "id_asc": "id",
        }

        dataset_name = self.request.query_params.get("dataset_name")
        llm_model_name = self.request.query_params.get("llm_model_name")
        sort_criteria = self.request.query_params.get("sort_criteria", "id_desc")

        if dataset_name:
            queryset = queryset.filter(dataset__name=dataset_name)
        if llm_model_name:
            queryset = queryset.filter(llm_model__name=llm_model_name)

        if sort_criteria in ["time_desc", "time_asc"]:
            queryset = queryset.annotate(execution_time=F('completed_at') - F('started_at'))

        sort_expr = sort_map.get(sort_criteria, "-id")  # Default: recent first
        queryset = queryset.order_by(sort_expr)

        return queryset

    def create(self, request, *args, **kwargs):
        """
        Override default POST to evaluate the dataset with a specific LLM model and compute test metrics.
        """
        serializer = TestCreationSerializer(data=request.data, context={'request': request})

        if serializer.is_valid():
            test = serializer.save()
            test.started_at = timezone.now()
            async_to_sync(evaluate_llm)(test)
            test.completed_at = timezone.now()

            compute_test_metrics(test)

            response_serializer = TestSerializer(test)
            return Response(response_serializer.data, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    # igual a get test ??? nsei se é necessario
    @action(detail=True, methods=['get'])
    def results(self, request, pk):
        """
        Get all question results for a specific test.
        """
        test = get_object_or_404(Test, id=pk, user=request.user)
        results = QuestionResult.objects.filter(test=test)
        serializer = QuestionResultSerializer(results, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'])
    def retry_failed(self, request, pk):
        """
        Retry failed questions (where answer is 'X') for a specific test.
        """
        try:
            test = get_object_or_404(Test, id=pk, user=request.user)

            # Obter todas as questões que falharam (answer == 'X') e pre-fetch dados relacionados
            failed_results = QuestionResult.objects.filter(test=test, answer="X").select_related('question',
                                                                                                 'test__llm_model')
            failed_results_list = list(failed_results)  # Evaluate the queryset synchronously
            print(f"Found {len(failed_results_list)} failed results for test {test.id}")

            if not failed_results_list:
                return Response(
                    {"message": "No failed questions to retry."},
                    status=status.HTTP_200_OK,
                    content_type='application/json'
                )

            # Pre-fetch correct_option for all questions
            question_ids = [result.question.id for result in failed_results_list]
            questions = Question.objects.filter(id__in=question_ids)
            correct_options = {q.id: q.correct_option for q in questions}

            async def retry_questions():
                semaphore = asyncio.Semaphore(SEMAPHORE_UNITS)

                async def limited_retry(data):
                    async with semaphore:
                        return await retry_query(
                            question_result=data['question_result'],
                            question=data['question'],
                            llm_model=data['llm_model'],
                            correct_option=data['correct_option']
                        )

                # Prepare data for each retry task
                tasks_data = [
                    {
                        'question_result': result,
                        'question': result.question,
                        'llm_model': result.test.llm_model,
                        'correct_option': correct_options.get(result.question.id, "")
                    }
                    for result in failed_results_list
                ]
                tasks = [limited_retry(data) for data in tasks_data]
                await asyncio.gather(*tasks)

            async_to_sync(retry_questions)()

            # Recalcula métricas do teste após o retry
            test.completed_at = timezone.now()
            compute_test_metrics(test)
            test.save()

            return Response(
                {"message": f"Retried {len(failed_results_list)} failed questions."},
                status=status.HTTP_200_OK,
                content_type='application/json'
            )

        except Exception as e:
            print(f"Unhandled exception in retry_failed: {str(e)}")
            return Response(
                {"error": f"Server error: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content_type='application/json'
            )

    @action(detail=False, methods=['delete'], url_path='delete-by-llm')
    def delete_by_llm(self, request):
        """
        Delete all tests for a given LLM model name.
        """
        llm_model_name = request.data.get("llm_model_name")

        if not llm_model_name:
            return Response(
                {"error": "Missing required parameter: llm_model_name"},
                status=status.HTTP_400_BAD_REQUEST
            )

        tests_to_delete = Test.objects.filter(
            user=request.user,
            llm_model__name=llm_model_name
        )

        if not tests_to_delete.exists():
            return Response(
                {"message": f"No tests found for the model '{llm_model_name}'."},
                status=status.HTTP_404_NOT_FOUND
            )

        deleted_count, _ = tests_to_delete.delete()

        return Response(
            {
                "message": f"Successfully deleted {deleted_count} tests for LLM model '{llm_model_name}'."
            },
            status=status.HTTP_200_OK
        )

    @action(detail=False, methods=['delete'])
    def delete_by_llm_and_dataset(self, request):
        """
        Delete all tests related to a specific LLM model and dataset for the authenticated user.
        """
        llm_model_name = request.data.get("llm_model_name")
        dataset_name = request.data.get("dataset_name")

        if not llm_model_name or not dataset_name:
            return Response(
                {"error": "Missing required parameters: llm_model_name and/or dataset_name"},
                status=status.HTTP_400_BAD_REQUEST
            )

        tests_to_delete = Test.objects.filter(
            user=request.user,
            llm_model__name=llm_model_name,
            dataset__name=dataset_name
        )

        if not tests_to_delete.exists():
            return Response(
                {"message": "No tests found for the given LLM model and dataset."},
                status=status.HTTP_404_NOT_FOUND
            )

        deleted_count, _ = tests_to_delete.delete()

        return Response(
            {
                "message": f"Successfully deleted {deleted_count} questions for LLM model '{llm_model_name}' in dataset '{dataset_name}'."},
            status=status.HTTP_200_OK
        )


async def evaluate_llm(test, questions=None):
    """
    Runs the LLM model evaluation on all questions from the dataset.
    """

    semaphore = asyncio.Semaphore(SEMAPHORE_UNITS)

    async def limited_query(question, llm_model):
        async with semaphore:
            return await query_llm(llm_model, question)

    try:
        if questions is None:
            questions = await sync_to_async(list)(test.dataset.questions.all())

        llm_model = await sync_to_async(lambda: test.llm_model)()

        tasks = [limited_query(question, llm_model) for question in questions]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        q_results = []
        for question, result in zip(questions, results):
            if isinstance(result, Exception):
                print(f"Error processing question {question.id}: {result}")
                answer, explanation, response_time, content = "X", "Error during retry", 0.0, str(result)
            else:
                answer, explanation, response_time, content = result

            correct = (answer.strip().upper() == question.correct_option.strip().upper())

            q_results.append(QuestionResult(
                test=test,
                question=question,
                llm_response=content,
                answer=answer,
                explanation=explanation,
                correct=correct,
                response_time=response_time,
                confidence=0.0
            ))

        await sync_to_async(QuestionResult.objects.bulk_create)(q_results)

    except Exception as e:
        print(f"Error occurred during evaluation: {e}")


async def query_llm(llm_model, question, max_attempts=4, initial_delay=4):
    """
    Sends the question to the LLM model and retrieves the response with a retry mechanism.
    """

    prompt = (
        f"You are a cybersecurity expert. Your task is to select the correct answer to the multiple-choice question below.\n"
        f"Respond with the letter corresponding to the correct option (A, B, C, or D). Do not add explanations. Do not write anything else.\n"
        f"Strictly follow the response format provided below.\n\n"
        f"Question:\n{question.question}\n\n"
        f"Options:\n"
        f"A: {question.option_a}\n"
        f"B: {question.option_b}\n"
        f"C: {question.option_c}\n"
        f"D: {question.option_d}\n\n"
        f"### Response Format:\n"
        f"Answer: <Correct answer letter (A, B, C, or D)>\n\n"
        f"### Example Response:\n"
        f"Answer: C"
    )

    attempt = 0
    delay = initial_delay  # Start with the initial delay time

    while attempt < max_attempts:
        try:
            start_time = timezone.now()

            response = await client.chat.completions.create(
                model=llm_model.model_id,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=20000  # responsavel pelo erro empty response
            )

            response_time = (timezone.now() - start_time).total_seconds()

            if hasattr(response, "error"):
                error_code = response.error.get("code", "Unknown")
                error_message = response.error.get("message", "No message provided.")
                raise Exception(f"API Error {error_code}: {error_message}")

            content = response.choices[0].message.content.strip()

            if not content:
                print(f"Warning: Received empty response on attempt {attempt + 1}/{max_attempts}")
                attempt += 1
                await asyncio.sleep(delay)
                delay *= 2  # Exponential backoff
                continue

            # Extract answer using regex
            answer_match = re.search(r"Answer:\s*([A-D])", content, re.IGNORECASE)
            answer = answer_match.group(1).strip().upper() if answer_match else "X"

            # Return answer if valid, else retry
            if answer in ["A", "B", "C", "D"]:
                print(f"Succes on attempt {attempt + 1}/{max_attempts}")
                return answer, "Not implemented yet", response_time, content

            print(f"Warning: Unexpected response format on attempt {attempt + 1}/{max_attempts}")
            attempt += 1
            await asyncio.sleep(delay)
            delay *= 2


        except Exception as e:
            error_msg = str(e)
            print(f"Error on attempt {attempt + 1}/{max_attempts}: {error_msg}")
            attempt += 1
            await asyncio.sleep(delay)
            delay *= 2  # Exponential backoff

    print("Failed to get a valid response after multiple retries")
    print("Question:", question.question)
    print("llm answer:", content)
    return "X", "X", 0.0, "Error Response:" + content


async def retry_query(question_result, question, llm_model, correct_option, max_attempts=5):
    """
    Reenvia a pergunta para o LLM. Mesmo que falhe, atualiza a resposta com uma mensagem de erro.
    """
    answer, explanation, response_time, content = await query_llm(llm_model, question, max_attempts=max_attempts)

    if answer not in ["A", "B", "C", "D"]:
        question_result.answer = "X"
        question_result.explanation = "O modelo não retornou uma opção válida após o retry."
        question_result.llm_response = content or "Resposta vazia ou inválida do modelo."
        question_result.correct = False
        question_result.response_time = 0.0
        question_result.confidence = 0.0
    else:
        correct = (answer.strip().upper() == correct_option.strip().upper())
        question_result.answer = answer
        question_result.explanation = explanation
        question_result.llm_response = content
        question_result.correct = correct
        question_result.response_time = response_time
        question_result.confidence = 0.0

    await sync_to_async(question_result.save)()


def compute_test_metrics(test):
    """
    Computes the test metrics.
    """
    results = QuestionResult.objects.filter(test=test)

    # Extract correct answers and predicted answers, filtering out 'X' (failed queries)
    y_true = [res.question.correct_option for res in results if res.answer != "X"]
    y_pred = [res.answer for res in results if res.answer != "X"]

    # General test statistics
    test.total_questions = len(results)
    test.correct_answers = sum(1 for i in range(len(y_true)) if y_true[i] == y_pred[i])
    test.accuracy_percentage = (test.correct_answers / len(y_true) * 100) if len(y_true) > 0 else 0
    test.failed_queries = sum(1 for res in results if res.answer == "X")

    ci_low, ci_high = calculate_confidence_interval(test.correct_answers, len(y_true))
    test.confidence_interval_low = ci_low
    test.confidence_interval_high = ci_high

    # Compute Precision, Recall, and F1-score for each class (A, B, C, D)
    class_metrics = {}
    if y_true and y_pred:
        classification_metrics = classification_report(y_true, y_pred, labels=['A', 'B', 'C', 'D'], output_dict=True, zero_division=0)

        for option in ['A', 'B', 'C', 'D']:
            class_metrics[option] = {
                "precision": classification_metrics.get(option, {}).get("precision", 0),
                "recall": classification_metrics.get(option, {}).get("recall", 0),
                "f1-score": classification_metrics.get(option, {}).get("f1-score", 0),
            }

        # Store class-based metrics as JSON
        test.class_metrics = class_metrics

        # Store macro average metrics
        test.precision_avg = classification_metrics["macro avg"]["precision"]
        test.recall_avg = classification_metrics["macro avg"]["recall"]
        test.f1_avg = classification_metrics["macro avg"]["f1-score"]

        # Store answer distribution as JSON
        test.answer_distribution = dict(Counter([res.answer for res in results]))

    test.save()


def calculate_confidence_interval(correct: int, total: int, alpha: float = 0.05):
    """
    Calcula o intervalo de confiança com o method de Wilson.
    """
    if total == 0:
        return 0.0, 0.0

    ci_low, ci_high = proportion_confint(correct, total, alpha=alpha, method='wilson')
    return ci_low * 100, ci_high * 100
