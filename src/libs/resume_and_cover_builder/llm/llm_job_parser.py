import os
import re  # для валидации email
import tempfile
import textwrap
from pathlib import Path

from dotenv import load_dotenv
from langchain_community.document_loaders import TextLoader
from langchain_community.embeddings import OpenAIEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_text_splitters import TokenTextSplitter
from loguru import logger

from src.job_sources.llm_provider import get_chat_llm
from src.libs.resume_and_cover_builder.utils import LoggerChatModel

# Загружаем переменные окружения из .env
load_dotenv()

# Настраиваем файл логов
log_folder = "log/resume/gpt_resume"
if not os.path.exists(log_folder):
    os.makedirs(log_folder)
log_path = Path(log_folder).resolve()
logger.add(
    log_path / "gpt_resume.log",
    rotation="1 day",
    compression="zip",
    retention="7 days",
    level="DEBUG",
)


class LLMParser:
    def __init__(self, openai_api_key):
        self.llm = LoggerChatModel(
            get_chat_llm(
                openai_api_key,
                temperature=0.4,
            )
        )
        self.llm_embeddings = OpenAIEmbeddings(
            openai_api_key=openai_api_key
        )  # инициализация эмбеддингов
        self.vectorstore = None  # создаётся после загрузки документа

    @staticmethod
    def _preprocess_template_string(template: str) -> str:
        """
        В этом классе не используется — унаследованный от других
        LLM-классов пакета метод dedent-а prompt-шаблонов, оставлен
        для единообразия сигнатуры между классами.
        """
        return textwrap.dedent(template)

    def set_body_html(self, body_html):
        """
        Разбивает HTML вакансии на чанки и индексирует в FAISS —
        так extract_* методы находят релевантный фрагмент вместо
        того, чтобы каждый раз передавать в LLM всю страницу
        целиком.
        """

        # TextLoader читает с диска, поэтому сохраняем HTML во
        # временный файл
        with tempfile.NamedTemporaryFile(
            delete=False, suffix=".html", mode="w", encoding="utf-8"
        ) as temp_file:
            temp_file.write(body_html)
            temp_file_path = temp_file.name
        try:
            loader = TextLoader(
                temp_file_path, encoding="utf-8", autodetect_encoding=True
            )
            document = loader.load()
            logger.debug("Document successfully loaded.")
        except Exception as e:
            logger.error(f"Error during document loading: {e}")
            raise
        finally:
            os.remove(temp_file_path)
            logger.debug(f"Temporary file removed: {temp_file_path}")

        # Разбиваем текст на чанки
        text_splitter = TokenTextSplitter(chunk_size=500, chunk_overlap=50)
        all_splits = text_splitter.split_documents(document)
        logger.debug(f"Text split into {len(all_splits)} fragments.")

        # Создаём векторное хранилище на FAISS
        try:
            self.vectorstore = FAISS.from_documents(
                documents=all_splits, embedding=self.llm_embeddings
            )
            logger.debug("Vectorstore successfully initialized.")
        except Exception as e:
            logger.error(f"Error during vectorstore creation: {e}")
            raise

    def _retrieve_context(self, query: str, top_k: int = 3) -> str:
        """Достаёт top_k наиболее релевантных фрагментов текста
        через retriever и склеивает их в одну строку."""
        if not self.vectorstore:
            raise ValueError(
                "Vectorstore not initialized. Run "
                "extract_job_description first."
            )

        retriever = self.vectorstore.as_retriever()
        retrieved_docs = retriever.get_relevant_documents(query)[:top_k]
        context = "\n\n".join(doc.page_content for doc in retrieved_docs)
        logger.debug(
            f"Context retrieved for query '{query}': {context[:200]}..."
        )  # логируем первые 200 символов
        return context

    def _extract_information(self, question: str, retrieval_query: str) -> str:
        """
        Единая точка «контекст из retriever + вопрос → LLM»: все
        extract_* ниже переиспользуют её вместо дублирования
        одинаковой логики retrieval + LLM-вызова для каждого поля.
        """
        context = self._retrieve_context(retrieval_query)

        prompt = ChatPromptTemplate.from_template(
            template="""
            You are an expert in extracting specific information from
            job descriptions.
            Carefully read the job description context below and
            provide a clear and concise answer to the question.

            Context: {context}

            Question: {question}
            Answer:
            """
        )

        formatted_prompt = prompt.format(context=context, question=question)
        logger.debug(
            f"Formatted prompt for extraction: {formatted_prompt[:200]}..."
        )  # логируем первые 200 символов

        try:
            chain = prompt | self.llm | StrOutputParser()
            result = chain.invoke({"context": context, "question": question})
            extracted_info = result.strip()
            logger.debug(f"Extracted information: {extracted_info}")
            return extracted_info
        except Exception as e:
            logger.error(f"Error during information extraction: {e}")
            return ""

    def extract_job_description(self) -> str:
        """Извлекает текст описания вакансии из HTML."""
        question = "What is the job description of the company?"
        retrieval_query = "Job description"
        logger.debug("Starting job description extraction.")
        return self._extract_information(question, retrieval_query)

    def extract_company_name(self) -> str:
        """Извлекает название компании из описания вакансии."""
        question = "What is the company's name?"
        retrieval_query = "Company name"
        logger.debug("Starting company name extraction.")
        return self._extract_information(question, retrieval_query)

    def extract_role(self) -> str:
        """Извлекает искомую должность/роль из вакансии."""
        question = "What is the role or title sought in this job description?"
        retrieval_query = "Job title"
        logger.debug("Starting role/title extraction.")
        return self._extract_information(question, retrieval_query)

    def extract_location(self) -> str:
        """Извлекает местоположение из описания вакансии."""
        question = "What is the location mentioned in this job description?"
        retrieval_query = "Location"
        logger.debug("Starting location extraction.")
        return self._extract_information(question, retrieval_query)

    def extract_recruiter_email(self) -> str:
        """
        LLM может ответить произвольным текстом вместо email
        (например, «not found») — проверка по regex ниже страхует
        вызывающий код от мусора вместо адреса.
        """
        question = (
            "What is the recruiter's email address in this job description?"
        )
        retrieval_query = "Recruiter email"
        logger.debug("Starting recruiter email extraction.")
        email = self._extract_information(question, retrieval_query)

        # Проверяем извлечённый email по regex
        email_regex = r"[\w\.-]+@[\w\.-]+\.\w+"
        if re.match(email_regex, email):
            logger.debug("Valid recruiter's email.")
            return email
        else:
            logger.warning("Invalid or not found recruiter's email.")
            return ""
