from PyQt5.QtGui import QColor
from add_answer import Ui_Form3
import sqlite3
from PyQt5.QtCore import Qt
from datetime import datetime as dt
from design import Ui_MainWindow
from calories_design import Ui_Form
from input_calories import Ui_Form2
import pymorphy2
from math import log, sin, cos, tan, sqrt
import xlrd
import sys
from PyQt5.QtWidgets import QMainWindow, QApplication, QWidget, QTableWidgetItem


def delete_unions_prep(sentence, subject, predicate):
    """
    Удаляются все служебные слова

    Parameters:
        sentence(str): предложение,
        subject(str): подлежащее,
        predicate(str): сказуемое

    Returns:
        result(str): предложение без служебных слов
    """
    words = []
    for word in sentence.split():
        morph = pymorphy2.MorphAnalyzer()
        parse = morph.parse(word)[0]
        if word != subject and word != predicate and \
                ('PREP' in parse.tag or 'CONJ' in parse.tag \
                 or 'PRCL' in parse.tag or 'INTJ' in parse.tag):
            continue
        words.append(word)
    return ' '.join(words)


def strip_punctuation_ru(data):
    """
        Убираются знаки препинания

        Parameters:
            data(str): строка, из которой нужно убрать знаки препинания

        Returns:
            result(str): строка без знаков препинания
        """
    punct = '\'!?;:,."-()'
    c_len = 0
    words = []
    word = ''
    while len(data) > c_len:
        if (data[c_len] in punct and not (data[c_len] == '-' and
                                          (' ' + data)[c_len - 1].isalpha() and
                                          (data + ' ')[c_len + 1].isalpha())) \
                or data[c_len] == ' ':
            if word.strip():
                words.append(word.strip())
                word = ''
        else:
            word += data[c_len]
        c_len += 1
    if word:
        words.append(word)

    return ' '.join(words)


class SpecialSymbolsError(Exception):
    pass


class NegativeArguments(Exception):
    pass


class OnlyDigitsError(Exception):
    pass


def math_expression(expression):
    """
    Вычисялется мат. выражение

    Parameters:
        expression(str): вычисляемое выражение

    Returns:
        eval(expression): сам результат
    """
    return eval(expression)


def insert_into_db_from_excel(con, xls):
    """Вставка данных из файла excel в бд.

    Parameters:
        con(sqlite3.Connection object):соединение с бд
        xls(str): название файла Excel

    Returns:
        None
        """
    cur = con.cursor()
    wb = xlrd.open_workbook(xls)
    needed_sheet = wb.sheets()[2]
    """берём первый лист"""
    for row in range(1, needed_sheet.nrows):
        values = []
        for col in range(needed_sheet.ncols):
            values.append(needed_sheet.cell(row, col).value)
        product, weigh, proteins, \
        fats, carbohydrates, calories, *rest = values
        cur.execute('''INSERT INTO Products (proteins, fats, carbohydrates, 
        calories, Title)
                       VALUES (?, ?, ?, ?, ?)''',
                    (proteins, fats, carbohydrates, calories, product.lower()))
        con.commit()


def try_to_predict(sentence, con, subject, predicate):
    """
    Используя бд phrases поиск возможных ответов.

    Parameters:
        sentence(str): анализируемое предложение
        con(sqlite3.Connection object): соединение с бд Phrases
        subject(str): подлежащее в предложении
        predicate(str): сказуемое в предложении

    Returns:
        most_relevant(str): предположительный ответ
    """
    cur = con.cursor()
    morph = pymorphy2.MorphAnalyzer()
    sentence = strip_punctuation_ru(sentence)
    possible_answers = [[], [], []]  # запись по степени уверенности
    delete_unions_prep(sentence.lower(), subject, predicate)
    mostly_relevant = cur.execute(f'''SELECT Answer
                                     FROM Possible_answers
                                     WHERE sentence LIKE "{sentence.lower()}" OR
            sentence LIKE "{delete_unions_prep(sentence.lower(),
                                               subject,
                                               predicate)}"''').fetchone()
    if mostly_relevant:
        if mostly_relevant[0]:
            return mostly_relevant[0]
    for word in sentence.split():
        initial_form = morph.parse(word)[0].normal_form
        can_be_relevant = cur.execute(f'''SELECT Possible_answer
                                         FROM Word_can_mean
                                         WHERE Word = "{word}" OR
                                         Word = "{initial_form}" OR
                                         Word = "{delete_unions_prep(word,
                                                                     subject,
                                                                     predicate)}" OR
                                         Word = "{delete_unions_prep(initial_form,
                                                                     subject, predicate)}"''').fetchall()
        if can_be_relevant:
            for variant in can_be_relevant:
                if variant:
                    possible_answers[0].append(variant[0])
        quite_irrelevant = cur.execute(f'''SELECT Possible_answer
                                          FROM Word_can_mean
                                          INNER JOIN Synonyms
                                          ON Synonyms.id = Word_can_mean.id
                                          WHERE Synonym = "{initial_form}" OR
                                          Synonym = "{word}" OR
                                          Synonym = "{delete_unions_prep(initial_form,
                                                                         subject,
                                                                         predicate)}" OR
                                          Synonym = "{delete_unions_prep(word,
                                                                         subject,
                                                                         predicate)}"''').fetchall()
        if quite_irrelevant:
            for variant in quite_irrelevant:
                if variant:
                    possible_answers[1].append(variant[0])
        only_relevant_by_theme = cur.execute(f'''SELECT Possible_answer
                                                FROM Word_can_mean
                                                INNER JOIN Themes
                                                ON Word_can_mean.Theme = Themes.id
                                                WHERE Word_can_mean.Theme = 
                                                "%{initial_form}%" OR 
                                                Word_can_mean.Theme = "%{word}%" OR
                                                Word_can_mean.Theme = 
                                                "%{delete_unions_prep(initial_form,
                                                                      subject,
                                                                      predicate)}%" OR 
                                                Word_can_mean.Theme = 
                                                "%{delete_unions_prep(word,
                                                                      subject,
                                                                      predicate)}%"''').fetchall()
        if only_relevant_by_theme:
            for variant in only_relevant_by_theme:
                if variant:
                    possible_answers[2].append(variant[0])
    if len(possible_answers[0]) > 0:
        most_relevant = find_most_relevant(possible_answers, 0,
                                           subject, predicate)
    elif len(possible_answers[1]) > 0:
        most_relevant = find_most_relevant(possible_answers, 1,
                                           subject, predicate)
    elif not all(possible_answers):
        return 'Не ноу'
    else:
        most_relevant = possible_answers[2][0]
    return most_relevant


def find_most_relevant(possible_answers, index, subject, predicate):
    """
    Учитываются повторения по другим критериям
    и есть ли подлежащие и сказуемое в варианте.

    Parameters:
        possible_answers(list): предположительные варианты по вероятности
        index(int): индекс проверяемой части предположительных ответов
        subject(str): подлежащее в предложении
        predicate(str): сказуемое в предложении

    Returns:
        most_relevant(str): наиболее подходящий вариант
    """
    most_relevant = possible_answers[index][0]
    maximum = 0  # таких же ответов по другим критериям
    for variant in possible_answers[index]:
        current_coincidences = 0
        if index + 1 <= len(possible_answers) - 1:
            current_coincidences += possible_answers[index + 1].count(variant)
        if index + 2 <= len(possible_answers) - 1:
            current_coincidences += possible_answers[index + 2].count(variant)
        current_coincidences += int(bool(subject) and subject in variant) + \
                                int(bool(predicate) and predicate in variant)
        if current_coincidences > maximum:
            most_relevant = variant
            maximum = current_coincidences
    if most_relevant:
        return most_relevant
    else:
        return 'Не знаю, что мне на это ответить'


class Window(QMainWindow, Ui_MainWindow):
    """
    Класс главного окна.

    Attributes:
        con_to_calories(sqlite3.Connection object): соединение с бд калории
        con_to_phrases(sqlite3.Connection object): соединение с юд phrases
        messages(QtWidgets.QTextEdit object): поле сообщений
        send(QtWidgets.QPushButton object): кнопка отправки сообщения
        analyzer(MessageAnalyzer object): анализатор
        get_user_answer(): открывает окно ввода
        speech(bool): включен ли режим 'Давай поболтаем'
        what_can(QtWidgets.QPushButton object): кнопка вызова функций бота
        math_btn(QtWidgets.QPushButton object): кнопка вызова вычисления выражения
        calories_btn(QtWidgets.QPushButton object): кнопка вызова окна калорий
        start_talk(QtWidgets.QPushButton object): кнопка старта диалога

    Methods:
        get_user_message(): получает сообщение пользователя и определяет тему
        what_can_send(): отправление информации о возможностях при нажатии кнопки
        start_calories_wnd(): открытие окна калорий при нажатии кнопки
        get_user_answer_wnd(): открытие окна ввода ответа пользователем
        get_math(): старт вычисления выражения
        start_talking(): старт диалога
       """

    def __init__(self):
        """
        Создаёт все необходимые аттрибуты для класса главного окна

        Parameters:
            None
        """
        super().__init__()
        self.setupUi(self)
        self.setWindowTitle('Говорилка')
        self.con_to_calories = sqlite3.connect('Calories.db')
        self.con_to_phrases = sqlite3.connect('Phrases.db')
        self.messages.addItem('Привет! Чем могу помочь? '
                              'Введите "Что ты можешь", '

                              'чтобы посмотреть, что я могу. \n'
                              'Готова поболтать даже без команды! :)\n'
                              'Для того чтобы прекратить наше общение,'
                              ' введите "хватит"')
        self.speech = True
        self.start_talk.setText('Хватит')
        self.send.clicked.connect(self.get_user_message)
        self.analyzer = MessageAnalyzer(self.con_to_phrases)
        self.get_user_answer.clicked.connect(self.get_user_answer_wnd)
        self.user_message = ''
        self.math_btn.clicked.connect(self.get_math)
        self.calories_btn.clicked.connect(self.start_calories_wnd)
        self.start_talk.clicked.connect(self.start_talking)
        self.what_can.clicked.connect(self.what_can_send)

    def get_user_message(self):
        """
        Получение сообщения пользователя из TextEdit и распределение по теме

        Parameters:
            None

        Returns:
            None
        """
        try:
            answer = ''
            user_message = self.user_message or self.input.toPlainText()
            self.messages.addItem(str(user_message)
                                  + ' ' + f'({str(dt.now().time().strftime("%H:%M"))})')
            permissible_letters = len(list(filter(lambda x: (x.isdigit()
                                                             or ord('А') <= ord(x) <= ord('я')
                                                             or ord('A') <= ord(x) <= ord('z')
                                                             or x in '";:.,?!\'()'
                                                             or x.lower() == 'ё'),
                                                  user_message)))
            self.messages.scrollToBottom()
            user_message = user_message.lower().strip()
            if not 'сколько будет' in user_message:
                if permissible_letters != len(user_message.replace(' ', '')):
                    raise SpecialSymbolsError
                elif len(list(filter(lambda x: x.isdigit(),
                                     user_message))) == len(user_message):
                    raise OnlyDigitsError
                user_message = strip_punctuation_ru(user_message)
            if "давай поболтаем" in user_message:
                answer += 'Для того чтобы прекратить наше общение,' \
                          ' введите "хватит" или нажмите кнопку'
                self.start_talk.setText('Хватит')
                self.speech = True
            elif "хватит" in user_message:
                answer = 'Хорошо, захотите поболтать ещё, введите ' \
                         '"Давай поболтаем" или нажмите соответствующую кнопку'
                self.speech = False
                self.start_talk.setText('Давай поболтаем')
            elif self.speech:
                answer = self.analyzer.speech(user_message)
            elif "сколько будет" in user_message:
                try:
                    answer = f"{math_expression(''.join(user_message.split()[2:])):.2f}"
                except NameError:
                    answer = 'Весело, конечно, но в математике цифры :)'
                except ZeroDivisionError:
                    answer = 'Ай-ай-ай, делить на ноль вы когда научились?'
            elif "что ты можешь" in user_message:
                answer = 'Я могу вычислить ' \
                         'математическое выражения,\n' \
                         'для запуска этого модуля ' \
                         'введите "Сколько будет \'выражение\'" или нажать кнопку,\n' \
                         'Доступны функции умножения 2 * 2 = 4, вычитания 2 - 2 = 0, \n' \
                         'сложения 2 + 3 = 5, деления 2 \\ 2 = 1, логарифм - log(x, base),\n' \
                         'где x - число от которого берётся логарифм, а base - основание,\n' \
                         'возведение в степень 2 ** 3 = 8,\n' \
                         'sin(x), cos(x), tan(x), ctg = 1 / tan(x),' \
                         'x в радианах, корень sqrt(4) = 2\n' \
                         'Также я могу посчитать калории продукта, ' \
                         'для вызова этого модуля ' \
                         'введите "Посчитай калории"\n' \
                         'или нажмите соответствующую кнопку. \n' \
                         'И конечно же, можем просто поболтать,\n' \
                         'для этого введите "Давай поболтаем"'
            elif "посчитай калории" in user_message:
                self.messages.addItem('Запускаю модуль калории')
                self.calories_wnd = WindowCalories(self.con_to_calories)
                self.calories_wnd.show()
            else:
                answer = 'Хм, вы не выбрали ниодного модуля, нахожусь в режиме ожидания'
            if answer:
                self.messages.addItem(answer + ' ' +
                                      f'({str(dt.now().time().strftime("%H:%M"))})')
            self.messages.scrollToBottom()
            self.user_message = ''
        except SpecialSymbolsError:
            self.messages.addItem('А вы часто в общении'
                                  ' спецсимволы используете? '
                                  '#непонимаюспецсимволы' + ' ' +
                                  f'({str(dt.now().time().strftime("%H:%M"))})')
        except OnlyDigitsError:
            self.messages.addItem('10000101111 тоже так могу, '
                                  'давайте и буквы использовать :)' + ' ' +
                                  f'({str(dt.now().time().strftime("%H:%M"))})')

    def what_can_send(self):
        """Вывод функций бота."""
        self.start_talk.setText('Давай поболтаем')
        self.speech = False
        self.user_message = 'Что ты можешь'
        self.get_user_message()

    def start_calories_wnd(self):
        """Открытие окна калорий."""
        self.start_talk.setText('Давай поболтаем')
        self.speech = False
        self.user_message = 'Посчитай калории'
        self.get_user_message()

    def get_user_answer_wnd(self):
        """Открытие окна ввода ответа пользователем."""
        self.wnd = InputUserAnswer(self.con_to_phrases)
        self.wnd.show()

    def get_math(self):
        """Запуск модуля вычисления выражения"""
        self.start_talk.setText('Давай поболтаем')
        self.speech = False
        self.messages.addItem('Введите выражение и нажмите кнопку')
        self.input.setText('Сколько будет ')

    def start_talking(self):
        """Старт диалога"""
        self.user_message = self.sender().text()
        self.get_user_message()


class InputUserAnswer(QWidget, Ui_Form3):
    """
    Класс ввода возможного ответа в таблицу Possible_answers.

    Attributes:
        con(sqlite3.Connection object): соединение с бд Phrases
        save_answer(QtWidgets.QPushButton): кнопка записи в бд

    Methods:
        add_possible_answer(): Вставка ответа пользователя в Possible_answers
    """

    def __init__(self, con):
        """
        Создаёт все необходимые аттрибуты для класса ввода ответа

        Parameters:
            con(sqlite3.Connection object): соединение с бд Phrases
        """
        super(InputUserAnswer, self).__init__()
        self.setupUi(self)
        self.setWindowTitle('Ввод возможного ответа')
        self.con = con
        self.save_answer.clicked.connect(self.add_possible_answers)

    def add_possible_answers(self):
        """
        Вставка ответа пользователя в Possible_answers.

        Parameters:
            None

        Returns:
            None
        """
        try:
            if self.sentence.toPlainText() and self.answer.toPlainText():
                cur = self.con.cursor()
                cur.execute(f'''INSERT INTO Possible_answers (sentence, Answer)
                           VALUES ("{self.sentence.toPlainText().lower()}",
                           "{self.answer.toPlainText()}")''')
                self.con.commit()
            else:
                raise ValueError
        except sqlite3.IntegrityError:
            self.msg.setText('Похоже введены неверные данные')
            return
        except ValueError:
            self.msg.setText('Вы не ввели данные во все поля')
            return
        self.msg.setText('Данные успешно записаны')


class MessageAnalyzer:
    """
    Анализатор сообщений.

    Attributes:
        subject(str): подлежащее в предложении
        predicate(str): сказуемое в предложении
        con(sqlite3.Connection object): соединение с бд Phrases

    Methods:
        speech(sentence): речь программы
        find_subject(sentence): поиска подлежащего
        find_predicate(sentence): поиск сказуемого
    """

    def __init__(self, con):
        """
        Создаёт все необходимые аттрибуты для класса анализатора

        Parameters:
            con(sqlite3.Connection object): соединение с бд Phrases
        """
        self.subject = ''
        self.predicate = ''
        self.con = con

    def speech(self, sentence):
        """
        Речь программы. Поиск подлежащего, сказуемого
        и попытка угадать ответ.

        Parameters:
            sentence(str): предложение

        Returns:
            result(str): предположтельный ответ
        """
        self.find_subject(sentence)
        self.find_predicate(sentence)
        return try_to_predict(sentence, self.con, self.subject,
                              self.predicate)

    def find_subject(self, sentence):
        """Нахождение самого вероятного подлежащего
        (без учёта предложений с тире между подлежащим и сказемым).

        Parameters:
            sentence(str): предложение

        Returns:
            None
        """
        """Так как часто в нашей речи мы используем подлежащее
         в качестве темы. Например, какая сегодня погода, 
         погода - подлежащее и является темой вопроса"""
        morph = pymorphy2.MorphAnalyzer()
        possible_subjects = []
        for word in sentence.split():
            parses = morph.parse(word)
            for parse in parses:
                if (parse.tag.POS == 'NOUN'
                    or parse.tag.POS == 'NPRO') \
                        and parse.tag.case == 'nomn':
                    possible_subjects.append((word, parse.score, parse))
                    break
                    # дальше будем выбирать по score
        if possible_subjects:
            most_possible_subject = sorted(possible_subjects,
                                           key=lambda x: -x[1])[0]
            self.subject = most_possible_subject
        else:
            self.subject = ''

    def find_predicate(self, sentence):
        """
        Нахождение самого вероятного сказуемого,
        как и в случае с подлежащим без предложений с тире.

        Parameters:
            sentence(str): предложение

        Returns:
            None"""
        """Пока не работает для сказуемых типа можем сделать"""
        morph = pymorphy2.MorphAnalyzer()
        subject = self.subject or self.find_subject(sentence)
        possible_predicates = []
        if subject:
            """сказуемое должно сочетаться с подлежащим
             по роду и числу"""
            for word in sentence.split():
                parses = morph.parse(word)
                subject_parse = self.subject[2]
                for parse in parses:
                    if (parse.tag.POS == 'VERB' and
                            parse.tag.number == subject_parse.tag.number
                            and parse.tag.gender == subject_parse.tag.gender):
                        possible_predicates.append((word, parse.score))
                        # дальше будем выбирать по score
            self.subject = self.subject[0]
        else:
            """Поиск категорий состояния, 
            то есть данное предложение - односоставное.
            В таком предложении крайне сложно определить,
            какой глагол является сказуемым, 
            поэтому просто ищем все глаголы в предложении"""
            for word in sentence.split():
                parses = morph.parse(word)
                for parse in parses:
                    if parse.tag.POS == 'VERB':
                        possible_predicates.append((word, parse.score))
                        # дальше будем выбирать по score
        if possible_predicates:
            most_possible_predicate = sorted(possible_predicates,
                                             key=lambda x: x[1])[0]
            self.predicate = most_possible_predicate[0]
        else:
            self.predicate = ''


class WindowCalories(QWidget, Ui_Form):
    """
    Окно вывода калорий в виде таблицы.

    Attributes:
        con(sqlite3.Connection object): соединение с бд калории
        count(QtWidgets.QPushButton): кнопка вывода калорий
        start_wnd_with_user_variant(QtWidgets.QPushButton):
        кнопка запуска окна записи в бд калории

    Methods:
        find_calories(): поиск заданного продукта в бд
        make_table(result): вывод результата в виде таблицы
        user_write_in_calories(): открытие окна записи в бд
    """

    def __init__(self, con):
        """
        Создаёт все необходимые аттрибуты для класса окна калорий

        Parameters:
            con(sqlite3.Connection object): соединение с бд калории
        """
        super().__init__()
        self.setupUi(self)
        self.con = con
        self.setWindowTitle('Калории')
        self.count.clicked.connect(self.find_calories)
        self.start_wnd_with_user_variant.clicked.connect(
            self.user_write_in_calories)

    def find_calories(self):
        """
        Поиск в базе данных и вызов функции создания таблицы.

        Parameters:
            None

        Returns:
            None
        """
        cur = self.con.cursor()
        result = cur.execute(f'''SELECT Title, Calories, proteins,
                                fats, carbohydrates
                                 FROM Products
                                 WHERE Title = 
                                "{self.input.text().lower()}"''').fetchall()
        if result:
            self.make_table(result)
        else:
            maybe_result = []
            for word in self.input.text().split():
                result = cur.execute(f'''SELECT Title, Calories,
                                proteins, fats, carbohydrates
                                 FROM Products
                                 WHERE Title LIKE 
                                "%{word}%"''').fetchall()
                if result and result not in maybe_result:
                    maybe_result.append(result)
            if maybe_result:
                self.make_table(*maybe_result)
            else:
                self.user_write_in_calories()

    def make_table(self, result):
        """
        Создание таблицы.

        Parameters:
            result(list): результат

        Returns:
            None
        """
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(['Название',
                                              'Калории',
                                              'Белки',
                                              'Жиры',
                                              'Углеводы'])
        self.table.setRowCount(0)
        if result:
            for row, line in enumerate(result):
                self.table.setRowCount(self.table.rowCount() + 1)
                for column, elem in enumerate(line):
                    if type(elem) != str:
                        elem = str(f'{elem:.2f}')
                    self.table.setItem(row, column,
                                       (QTableWidgetItem(str(elem))))
                    self.table.item(row, column).setBackground(QColor('#ffffff'))
            self.table.resizeColumnsToContents()
            self.table.resizeRowsToContents()

    def user_write_in_calories(self):
        """
        Вставка ответа пользователя в Calories.

        Parameters:
            None

        Returns:
            None
        """
        self.wnd_user_variant = InputCalories(self.con)
        self.wnd_user_variant.show()


class InputCalories(QWidget, Ui_Form2):
    """
    Ввод калорий пользователем.

    Attributes:
        con(sqlite3.Connection object): соединение с бд калории
        save(QtWidgets.QPushButton): кнопка записи

    Methods:
        write_in_calories(): вставка в бд данных
    """

    def __init__(self, con):
        """
        Создаёт все необходимые аттрибуты для класса окна калорий

        Parameters:
            con(sqlite3.Connection object): соединение с бд калории
        """
        super(InputCalories, self).__init__()
        self.setupUi(self)
        self.setWindowTitle('Ввод калорий')
        self.con = con
        self.save.clicked.connect(self.write_in_calories)

    def write_in_calories(self):
        """Вставка в бд введённых пользователем бжу и калорий
        в базе данных стоит проверка введённых данных по калориям.
        Соотношение (калории = 4 * белки + 9 * жиры + 4 * углеводы).

        Parameters:
            None

        Returns:
            None
        """
        try:
            if int(self.proteins.text()) < 0 or \
                    int(self.carbohydrates.text()) < 0 \
                    or int(self.fats.text()) < 0:
                raise NegativeArguments
            if not self.title.text() or not self.proteins.text() \
                    or not self.carbohydrates.text() or not self.fats.text() \
                    or not self.calories.text():
                raise ValueError
            cur = self.con.cursor()
            cur.execute('''INSERT INTO Products (Title, proteins,
                            carbohydrates, fats, calories)
                           VALUES (?, ?, ?, ?, ?)''',
                        (self.title.text(), self.proteins.text(),
                         self.carbohydrates.text(), self.fats.text(),
                         self.calories.text()))
            self.con.commit()
            self.error.setText('Данные успешно записаны')
        except sqlite3.IntegrityError:
            self.error.setText('Такой продукт уже есть или '
                               'Введены данные в неверном соотношении '
                               'к = блк * 4 + 9 * ж + 4 * у')
            return False
        except NegativeArguments:
            self.error.setText('Недопустимы отрицательные значения')
        except ValueError:
            self.error.setText('Заполнены не все обязательные поля')


if __name__ == '__main__':
    app = QApplication(sys.argv)
    wnd = Window()
    wnd.show()
    sys.exit(app.exec())
