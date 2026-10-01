from unittest.mock import MagicMock, patch

from src.job_sources.headhunter.browser_replies import (
    fetch_new_employer_messages,
    send_chat_cover_letter,
    send_chat_cover_letter_result,
    send_reply,
)


def test_send_chat_cover_letter_finds_chat_by_negotiation_url():
    """HH больше не всегда помечает ссылку чата data-qa с ``chat``."""
    driver = MagicMock()
    negotiation = MagicMock()
    vacancy_link = MagicMock()
    vacancy_link.get_attribute.return_value = "https://hh.ru/vacancy/123"
    chat_link = MagicMock()
    chat_link.get_attribute.return_value = (
        "https://hh.ru/applicant/negotiations/456"
    )

    driver.find_elements.return_value = [negotiation]

    def find_links(_by, selector):
        if 'href*="/vacancy/"' in selector:
            return [vacancy_link]
        if 'href*="/applicant/negotiations/"' in selector:
            return [chat_link]
        return []

    negotiation.find_elements.side_effect = find_links

    with patch("src.job_sources.headhunter.browser_replies.time.sleep"), patch(
        "src.job_sources.headhunter.browser_replies.send_reply",
        return_value=True,
    ) as send_reply:
        sent = send_chat_cover_letter(driver, "123", "Здравствуйте")

    assert sent is True
    assert driver.get.call_args_list[-1].args == (
        "https://hh.ru/applicant/negotiations/456",
    )
    send_reply.assert_called_once_with(driver, "Здравствуйте")


def test_send_chat_cover_letter_opens_current_hh_chat_button():
    """На реальной странице переговоров HH чат открывается кнопкой."""
    driver = MagicMock()
    negotiation = MagicMock()
    vacancy_link = MagicMock()
    vacancy_link.get_attribute.return_value = "https://hh.ru/vacancy/123"
    open_chat = MagicMock()
    open_chat.get_attribute.return_value = None

    driver.find_elements.return_value = [negotiation]

    def find_controls(_by, selector):
        if 'href*="/vacancy/"' in selector:
            return [vacancy_link]
        if 'button[data-qa="open_chat"]' in selector:
            return [open_chat]
        return []

    negotiation.find_elements.side_effect = find_controls

    with patch("src.job_sources.headhunter.browser_replies.time.sleep"), patch(
        "src.job_sources.headhunter.browser_replies.send_reply",
        return_value=True,
    ) as send_reply:
        sent = send_chat_cover_letter(driver, "123", "Здравствуйте")

    assert sent is True
    open_chat.click.assert_called_once()
    send_reply.assert_called_once_with(driver, "Здравствуйте")


def test_send_chat_cover_letter_opens_chat_from_stored_vacancy_link_first():
    """Ссылка из журнала должна избавлять от обхода всех переговоров."""
    driver = MagicMock()
    open_chat = MagicMock()
    open_chat.get_attribute.return_value = None
    chat_frame = MagicMock()

    def find_elements(_by, selector):
        if 'button[data-qa="open_chat"]' in selector:
            return [open_chat]
        if 'iframe[src*="chatik.hh.ru/chat/"]' in selector:
            return [chat_frame]
        return []

    driver.find_elements.side_effect = find_elements

    with patch("src.job_sources.headhunter.browser_replies.time.sleep"), patch(
        "src.job_sources.headhunter.browser_replies.send_reply",
        return_value=True,
    ) as send_reply:
        sent = send_chat_cover_letter(
            driver,
            "123",
            "Здравствуйте",
            "https://hh.ru/vacancy/123",
        )

    assert sent is True
    driver.get.assert_called_once_with("https://hh.ru/vacancy/123")
    open_chat.click.assert_called_once()
    send_reply.assert_called_once_with(driver, "Здравствуйте")
    assert driver.switch_to.default_content.call_count == 2


def test_send_chat_cover_letter_result_recognizes_archived_vacancy():
    driver = MagicMock()
    driver.execute_script.return_value = "Вакансия в архиве"

    with patch("src.job_sources.headhunter.browser_replies.time.sleep"):
        result = send_chat_cover_letter_result(
            driver,
            "123",
            "Здравствуйте",
            "https://hh.ru/vacancy/123",
        )

    assert result.sent is False
    assert result.archived is True
    driver.find_elements.assert_not_called()


def test_send_chat_result_recognizes_authorization_unavailable_page():
    driver = MagicMock()
    driver.execute_script.return_value = (
        "The vacancy you are trying to open is not available under current "
        "authorization."
    )

    with patch("src.job_sources.headhunter.browser_replies.time.sleep"):
        result = send_chat_cover_letter_result(
            driver,
            "123",
            "Здравствуйте",
            "https://hh.ru/vacancy/123",
        )

    assert result.sent is False
    assert result.archived is False
    assert result.unavailable is True
    driver.find_elements.assert_not_called()


def test_send_chat_cover_letter_switches_into_hh_chatik_frame():
    driver = MagicMock()
    negotiation = MagicMock()
    vacancy_link = MagicMock()
    vacancy_link.get_attribute.return_value = "https://hh.ru/vacancy/123"
    open_chat = MagicMock()
    open_chat.get_attribute.return_value = None
    chat_frame = MagicMock()

    def find_elements(_by, selector):
        if "negotiations-item" in selector:
            return [negotiation]
        if 'iframe[src*="chatik.hh.ru/chat/"]' in selector:
            return [chat_frame]
        return []

    def find_controls(_by, selector):
        if 'href*="/vacancy/"' in selector:
            return [vacancy_link]
        if 'button[data-qa="open_chat"]' in selector:
            return [open_chat]
        return []

    driver.find_elements.side_effect = find_elements
    negotiation.find_elements.side_effect = find_controls

    with patch("src.job_sources.headhunter.browser_replies.time.sleep"), patch(
        "src.job_sources.headhunter.browser_replies.send_reply",
        return_value=True,
    ):
        sent = send_chat_cover_letter(driver, "123", "Здравствуйте")

    assert sent is True
    driver.switch_to.frame.assert_called_once_with(chat_frame)


def test_fetch_new_employer_messages_opens_current_hh_chat_button():
    driver = MagicMock()
    negotiation = MagicMock()
    vacancy_link = MagicMock()
    vacancy_link.get_attribute.return_value = "https://hh.ru/vacancy/123"
    open_chat = MagicMock()
    open_chat.get_attribute.return_value = None
    chat_frame = MagicMock()
    message = MagicMock()
    message.get_attribute.return_value = "chat-message"
    message.text = "Добрый день, расскажите о себе"

    def find_elements(_by, selector):
        if "negotiations-item" in selector:
            return [negotiation]
        if 'iframe[src*="chatik.hh.ru/chat/"]' in selector:
            return [chat_frame]
        if "chat-message" in selector:
            return [message]
        return []

    def find_controls(_by, selector):
        if 'href*="/vacancy/"' in selector:
            return [vacancy_link]
        if 'button[data-qa="open_chat"]' in selector:
            return [open_chat]
        return []

    driver.find_elements.side_effect = find_elements
    negotiation.find_elements.side_effect = find_controls

    with patch("src.job_sources.headhunter.browser_replies.time.sleep"):
        messages = fetch_new_employer_messages(driver)

    assert messages == [
        {
            "external_id": "123",
            "message_id": "Добрый день, расскажите о себе",
            "text": "Добрый день, расскажите о себе",
        }
    ]
    open_chat.click.assert_called_once()


def test_send_reply_uses_hh_chatik_input_and_send_button():
    driver = MagicMock()
    text_input = MagicMock()
    send_button = MagicMock()

    def find_elements(_by, selector):
        if 'textarea[data-qa="text-input"]' in selector:
            return [text_input]
        if 'button[data-qa="chatik-do-send-message"]' in selector:
            return [send_button]
        return []

    driver.find_elements.side_effect = find_elements

    with patch("src.job_sources.headhunter.browser_replies.time.sleep"):
        sent = send_reply(driver, "Здравствуйте")

    assert sent is True
    text_input.send_keys.assert_called_once_with("Здравствуйте")
    send_button.click.assert_called_once()


def test_send_chat_cover_letter_finds_vacancy_on_later_negotiations_page():
    driver = MagicMock()
    first_page_item = MagicMock()
    first_page_link = MagicMock()
    first_page_link.get_attribute.return_value = "https://hh.ru/vacancy/111"
    second_page_item = MagicMock()
    second_page_link = MagicMock()
    second_page_link.get_attribute.return_value = "https://hh.ru/vacancy/123"
    open_chat = MagicMock()
    open_chat.get_attribute.return_value = None
    chat_frame = MagicMock()
    first_page_button = MagicMock()
    second_page_button = MagicMock()
    page = {"number": 1}

    def switch_to_second_page():
        page["number"] = 2

    second_page_button.click.side_effect = switch_to_second_page

    def find_elements(_by, selector):
        if "negotiations-item" in selector:
            return (
                [first_page_item]
                if page["number"] == 1
                else [second_page_item]
            )
        if 'button[data-qa^="number-pages-"]' in selector:
            return [first_page_button, second_page_button]
        if 'button[data-qa^="number-pages-2"]' in selector:
            return [second_page_button]
        if 'iframe[src*="chatik.hh.ru/chat/"]' in selector:
            return [chat_frame]
        return []

    def first_page_controls(_by, selector):
        if 'href*="/vacancy/"' in selector:
            return [first_page_link]
        return []

    def second_page_controls(_by, selector):
        if 'href*="/vacancy/"' in selector:
            return [second_page_link]
        if 'button[data-qa="open_chat"]' in selector:
            return [open_chat]
        return []

    driver.find_elements.side_effect = find_elements
    first_page_item.find_elements.side_effect = first_page_controls
    second_page_item.find_elements.side_effect = second_page_controls

    with patch("src.job_sources.headhunter.browser_replies.time.sleep"), patch(
        "src.job_sources.headhunter.browser_replies.send_reply",
        return_value=True,
    ):
        sent = send_chat_cover_letter(driver, "123", "Здравствуйте")

    assert sent is True
    second_page_button.click.assert_called_once()
    open_chat.click.assert_called_once()
