import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import subprocess
import os
import platform
import psutil
import time
import threading
import webbrowser

class ApplicationInterface:
    def __init__(self, root):
        self.root = root
        self.root.title("Единый интерфейс оптимизации расписания")
        self.root.geometry("800x600")
        
        # Переменные для хранения состояния
        self.program_directory = None
        self.selected_xlsx_file = None
        self.terminal_process = None
        self.flask_process = None  # Для отдельного процесса flask-сервера
        
        # Создание основного фрейма
        main_frame = ttk.Frame(root, padding="20")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Заголовок
        title_label = ttk.Label(main_frame, text="Управление оптимизацией", font=("Arial", 16, "bold"))
        title_label.pack(pady=10)
        
        # Информационная панель
        info_frame = ttk.LabelFrame(main_frame, text="Информация")
        info_frame.pack(fill=tk.X, pady=10)
        
        self.dir_label = ttk.Label(info_frame, text="Рабочий каталог: не выбран")
        self.dir_label.pack(anchor=tk.W, padx=10, pady=5)
        
        self.file_label = ttk.Label(info_frame, text="Выбранный файл: не выбран")
        self.file_label.pack(anchor=tk.W, padx=10, pady=5)
        
        # Контейнер для кнопок
        buttons_frame = ttk.Frame(main_frame)
        buttons_frame.pack(fill=tk.BOTH, expand=True, pady=10)
        
        # Создание кнопок с номерами (теперь с новой структурой)
        self.create_single_button(buttons_frame, "1. Выбрать рабочий каталог", self.select_directory, 0)
        self.create_double_button_row(buttons_frame, 
                                    "2. Запустить оптимизацию", self.run_scheduler,
                                    "2.1. Открыть оптимизированное расписание", self.open_optimized_schedule, 1)
        self.create_triple_button_row(buttons_frame,
                                    "3. Создать веб-приложение", self.run_gear_xls,
                                    "3.1. Запустить flask-сервер", self.run_flask_server,
                                    "3.2. Открыть веб-приложение", self.open_web_app, 2)
        # Изменяем строку 4 на тройную кнопку
        self.create_triple_button_row(buttons_frame,
                                    "4. Запустить визуализатор", self.run_visualiser,
                                    "4.1. Открыть PDF-визуализацию", self.open_pdf_visualization,
                                    "4.2. Открыть HTML-визуализацию", self.open_html_visualization, 3)
        self.create_single_button(buttons_frame, "5. Выбрать .xlsx файл", self.select_xlsx_file, 4)
        self.create_double_button_row(buttons_frame,
                                    "6. Конвертировать в .xlsm", self.convert_to_xlsm,
                                    "6.1. Открыть .xlsm файл", self.open_xlsm_file, 5)
        self.create_double_button_row(buttons_frame,
                                    "7.0. Открыть новые предпочтения", self.open_newpref,
                                    "7. Учесть изменения", self.run_scheduler_newpref, 6)
        
        # Лог действий
        log_frame = ttk.LabelFrame(main_frame, text="Лог действий")
        log_frame.pack(fill=tk.BOTH, expand=True, pady=10)
        
        self.log_text = tk.Text(log_frame, height=10, width=80, wrap=tk.WORD)
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Добавляем скроллбар для лога
        scrollbar = ttk.Scrollbar(self.log_text, command=self.log_text.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.config(yscrollcommand=scrollbar.set)
        
        # Статус бар
        self.status_bar = ttk.Label(root, text="Готов к работе", relief=tk.SUNKEN, anchor=tk.W)
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)
    
    def create_single_button(self, parent, text, command, row):
        """Создает кнопку на всю ширину"""
        btn = ttk.Button(parent, text=text, command=command, width=30)
        btn.pack(fill=tk.X, pady=5, padx=20)
    
    def create_double_button_row(self, parent, text1, command1, text2, command2, row):
        """Создает две кнопки в одной строке (50% на 50%)"""
        row_frame = ttk.Frame(parent)
        row_frame.pack(fill=tk.X, pady=5, padx=20)
        
        btn1 = ttk.Button(row_frame, text=text1, command=command1)
        btn1.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        
        btn2 = ttk.Button(row_frame, text=text2, command=command2)
        btn2.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(5, 0))
    
    def create_triple_button_row(self, parent, text1, command1, text2, command2, text3, command3, row):
        """Создает три кнопки в одной строке (33% на 33% на 34%)"""
        row_frame = ttk.Frame(parent)
        row_frame.pack(fill=tk.X, pady=5, padx=20)
        
        btn1 = ttk.Button(row_frame, text=text1, command=command1)
        btn1.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 3))
        
        btn2 = ttk.Button(row_frame, text=text2, command=command2)
        btn2.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(3, 3))
        
        btn3 = ttk.Button(row_frame, text=text3, command=command3)
        btn3.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(3, 0))
    
    def log_action(self, message):
        """Добавляет сообщение в лог и обновляет статус"""
        timestamp = time.strftime("%H:%M:%S")
        self.log_text.insert(tk.END, f"[{timestamp}] {message}\n")
        self.log_text.see(tk.END)  # Прокрутка до конца
        self.status_bar.config(text=message)
        self.root.update()
    
    def select_directory(self):
        """Обработчик для кнопки 1: Выбор рабочего каталога"""
        directory = filedialog.askdirectory(title="Выберите рабочий каталог программы")
        if directory:
            self.program_directory = directory
            self.dir_label.config(text=f"Рабочий каталог: {directory}")
            self.log_action(f"Выбран рабочий каталог: {directory}")
    
    def open_optimized_schedule(self):
        """Обработчик для кнопки 2.1: Открытие оптимизированного расписания"""
        if not self.program_directory:
            messagebox.showwarning("Предупреждение", "Сначала выберите рабочий каталог программы")
            return
        
        file_path = os.path.join(self.program_directory, "visualiser", "optimized_schedule.xlsx")
        
        if not os.path.exists(file_path):
            messagebox.showwarning("Предупреждение", 
                                  f"Файл не найден: {file_path}")
            return
        
        try:
            if platform.system() == "Windows":
                os.startfile(file_path)
            elif platform.system() == "Darwin":  # macOS
                subprocess.Popen(["open", file_path])
            else:  # Linux и др.
                subprocess.Popen(["xdg-open", file_path])
            self.log_action(f"Открыт файл: {file_path}")
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось открыть файл: {e}")
    
    def run_flask_server(self):
        """Обработчик для кнопки 3.1: Запуск flask-сервера"""
        if not self.program_directory:
            messagebox.showwarning("Предупреждение", "Сначала выберите рабочий каталог программы")
            return
        
        # Проверяем, не запущен ли уже flask-сервер
        if self.is_process_running(self.flask_process):
            messagebox.showinfo("Информация", "Flask-сервер уже запущен")
            return
        
        self.log_action("Запуск flask-сервера...")
        
        # Определяем функцию для выполнения в отдельном потоке
        def run_in_thread():
            self.flask_process = self.start_new_terminal_with_commands()
            # Добавляем сообщение в лог после запуска
            time.sleep(1)  # Небольшая пауза, чтобы терминал успел открыться
            self.log_action("Терминал flask-сервера запущен. Пока окно терминала открыто Вы можете экспортировать расписание из веб-приложения в эксель-файл")
        
        # Запускаем в отдельном потоке
        threading.Thread(target=run_in_thread, daemon=True).start()
    
    def start_new_terminal_with_commands(self):
        """Запускает новый терминал с командами для flask-сервера"""
        system = platform.system()
        
        if system == "Windows":
            # Для Windows создаем bat-файл с правильным рабочим каталогом
            bat_file = os.path.join(self.program_directory, "start_flask.bat")
            
            # Создаем bat-файл, который установит правильный рабочий каталог
            with open(bat_file, "w") as f:
                f.write(f'@echo off\n')
                f.write(f'cd /d "{self.program_directory}"\n')
                f.write(f'cd /d gear_xls\n')
                f.write(f'python server_routes.py\n')
                f.write(f'pause\n')  # Пауза, чтобы окно не закрывалось
            
            # Запускаем новое окно cmd с bat-файлом
            cmd = ["cmd.exe", "/C", f"start cmd /K {bat_file}"]
            return subprocess.Popen(cmd, cwd=self.program_directory)
        
        elif system == "Darwin":  # macOS
            # Создаем AppleScript для открытия нового Terminal
            script = f'''
            tell application "Terminal"
                do script "cd '{self.program_directory}' && python gear_xls/server_routes.py"
                activate
            end tell
            '''
            return subprocess.Popen(['osascript', '-e', script])
        
        else:  # Linux и другие Unix-подобные системы
            # Пробуем различные терминалы Linux
            terminals = [
                ("gnome-terminal", ["gnome-terminal", "--", "bash", "-c", f"cd '{self.program_directory}' && python gear_xls/server_routes.py; read"]),
                ("xterm", ["xterm", "-e", f"cd '{self.program_directory}' && python gear_xls/server_routes.py; read"]),
                ("konsole", ["konsole", "-e", f"cd '{self.program_directory}' && python gear_xls/server_routes.py; read"]),
                ("x-terminal-emulator", ["x-terminal-emulator", "-e", f"cd '{self.program_directory}' && python gear_xls/server_routes.py; read"])
            ]
            
            for term_name, cmd in terminals:
                try:
                    # Проверяем, доступен ли терминал
                    subprocess.run(["which", term_name], capture_output=True, text=True, check=True)
                    return subprocess.Popen(cmd)
                except:
                    continue
            
            # Если ничего не работает, возвращаемся к стандартному способу
            return subprocess.Popen(["bash", "-c", f"cd '{self.program_directory}' && python gear_xls/server_routes.py"])
    
    def open_web_app(self):
        """Обработчик для кнопки 3.2: Открытие веб-приложения"""
        if not self.program_directory:
            messagebox.showwarning("Предупреждение", "Сначала выберите рабочий каталог программы")
            return
        
        html_path = os.path.join(self.program_directory, "gear_xls", "html_output", "schedule.html")
        
        if not os.path.exists(html_path):
            messagebox.showwarning("Предупреждение", 
                                  f"Файл не найден: {html_path}")
            return
        
        try:
            webbrowser.open(f"file://{html_path}")
            self.log_action(f"Открыто веб-приложение: {html_path}")
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось открыть веб-приложение: {e}")
    
    def open_newpref(self):
        """Обработчик для кнопки 7.0: Открытие файла newpref.xlsx"""
        if not self.program_directory:
            messagebox.showwarning("Предупреждение", "Сначала выберите рабочий каталог программы")
            return
        
        file_path = os.path.join(self.program_directory, "xlsx_initial", "newpref.xlsx")
        
        if not os.path.exists(file_path):
            messagebox.showwarning("Предупреждение", 
                                  f"Файл не найден: {file_path}")
            return
        
        try:
            if platform.system() == "Windows":
                os.startfile(file_path)
            elif platform.system() == "Darwin":  # macOS
                subprocess.Popen(["open", file_path])
            else:  # Linux и др.
                subprocess.Popen(["xdg-open", file_path])
            self.log_action(f"Открыт файл: {file_path}")
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось открыть файл: {e}")
    
    def select_xlsx_file(self):
        """Обработчик для кнопки 5: Выбор .xlsx файла"""
        if not self.program_directory:
            messagebox.showwarning("Предупреждение", "Сначала выберите рабочий каталог программы")
            return
        
        # Изменено: теперь ищем в подкаталоге gear_xls/excel_exports
        excel_dir = os.path.join(self.program_directory, "gear_xls", "excel_exports")
        if not os.path.exists(excel_dir):
            messagebox.showwarning("Предупреждение", 
                                  f"Каталог gear_xls/excel_exports не найден в {self.program_directory}")
            return
        
        xlsx_file = filedialog.askopenfilename(
            title="Выберите .xlsx файл",
            initialdir=excel_dir,
            filetypes=[("Excel файлы", "*.xlsx")]
        )
        
        if xlsx_file:
            self.selected_xlsx_file = xlsx_file
            filename = os.path.basename(xlsx_file)
            self.file_label.config(text=f"Выбранный файл: {filename}")
            self.log_action(f"Выбран файл: {filename}")
    
    def is_process_running(self, process):
        """Проверяет, активен ли процесс"""
        if not process:
            return False
        try:
            return process.poll() is None
        except:
            return False
    
    def get_terminal_command(self):
        """Возвращает команду для запуска терминала в зависимости от ОС"""
        if platform.system() == "Windows":
            return ["cmd.exe", "/K"]
        elif platform.system() == "Darwin":  # macOS
            return ["open", "-a", "Terminal"]
        else:  # Linux и др.
            # Проверяем наличие различных терминалов
            terminals = ["gnome-terminal", "xterm", "konsole"]
            for term in terminals:
                try:
                    subprocess.run(["which", term], capture_output=True, text=True, check=False)
                    if term == "gnome-terminal":
                        return [term, "--"]
                    else:
                        return [term, "-e"]
                except:
                    continue
            # Если ни один из известных терминалов не найден
            return ["x-terminal-emulator", "-e"]
    
    def execute_in_terminal(self, commands, directory=None):
        """Выполняет команды в терминале"""
        if not directory and self.program_directory:
            directory = self.program_directory
        
        if not directory:
            messagebox.showwarning("Предупреждение", "Сначала выберите рабочий каталог программы")
            return None
        
        system = platform.system()
        
        if system == "Windows":
            # Для Windows объединяем команды с помощью & 
            full_command = " & ".join(commands)
            cmd = ["cmd.exe", "/K", f"cd /d {directory} & {full_command}"]
            return subprocess.Popen(cmd)
        
        elif system == "Darwin":  # macOS
            # Создаем скрипт с командами
            script_path = os.path.join(os.path.expanduser("~"), "temp_commands.sh")
            with open(script_path, "w") as script:
                script.write("#!/bin/bash\n")
                script.write(f"cd \"{directory}\"\n")
                for cmd in commands:
                    script.write(f"{cmd}\n")
            
            # Делаем скрипт исполняемым
            os.chmod(script_path, 0o755)
            
            # Запускаем Terminal с нашим скриптом
            return subprocess.Popen(["open", "-a", "Terminal", script_path])
        
        else:  # Linux и др.
            # Подобно macOS, создаем временный скрипт
            script_path = os.path.join("/tmp", "temp_commands.sh")
            with open(script_path, "w") as script:
                script.write("#!/bin/bash\n")
                script.write(f"cd \"{directory}\"\n")
                for cmd in commands:
                    script.write(f"{cmd}\n")
                script.write("bash\n")  # Оставляем оболочку открытой
            
            # Делаем скрипт исполняемым
            os.chmod(script_path, 0o755)
            
            # Определяем доступный терминал
            terminal_cmd = self.get_terminal_command()
            
            if terminal_cmd[0] == "gnome-terminal":
                return subprocess.Popen(terminal_cmd + [f"bash -c '{script_path}; bash'"])
            else:
                return subprocess.Popen(terminal_cmd + [f"bash {script_path}"])
    
    def run_scheduler(self):
        """Обработчик для кнопки 2: Запуск планировщика"""
        if not self.program_directory:
            messagebox.showwarning("Предупреждение", "Сначала выберите рабочий каталог программы")
            return
        
        self.log_action("Запуск планировщика...")
        
        # Команды для выполнения
        commands = [
            f"python main_sch.py xlsx_initial/schedule_planning.xlsx --time-limit 300 --verbose --time-interval 5"
        ]
        
        # Определяем функцию для выполнения в отдельном потоке
        def run_in_thread():
            self.terminal_process = self.execute_in_terminal(commands)
        
        # Запускаем в отдельном потоке, чтобы не блокировать GUI
        threading.Thread(target=run_in_thread, daemon=True).start()
    
    def run_gear_xls(self):
        """Обработчик для кнопки 3: Запуск gear_xls"""
        if not self.program_directory:
            messagebox.showwarning("Предупреждение", "Сначала выберите рабочий каталог программы")
            return
        
        self.log_action("Запуск gear_xls...")
        
        # Проверяем, запущен ли терминал
        if self.is_process_running(self.terminal_process):
            # Терминал уже запущен, но нам нужно проверить, активны ли процессы
            # На практике это сложно сделать межплатформенно, поэтому создаем новый терминал
            pass
        
        # Запускаем новый терминал с нужными командами
        gear_dir = os.path.join(self.program_directory, "gear_xls")
        commands = ["python main.py"]
        
        # Определяем функцию для выполнения в отдельном потоке
        def run_in_thread():
            self.terminal_process = self.execute_in_terminal(commands, gear_dir)
        
        # Запускаем в отдельном потоке
        threading.Thread(target=run_in_thread, daemon=True).start()
    
    def run_visualiser(self):
        """Обработчик для кнопки 4: Запуск визуализатора"""
        if not self.program_directory:
            messagebox.showwarning("Предупреждение", "Сначала выберите рабочий каталог программы")
            return
        
        self.log_action("Запуск визуализатора...")
        
        # Запускаем новый терминал с нужными командами
        visualiser_dir = os.path.join(self.program_directory, "visualiser")
        commands = ["python example_usage_enhanced.py"]
        
        # Определяем функцию для выполнения в отдельном потоке
        def run_in_thread():
            self.terminal_process = self.execute_in_terminal(commands, visualiser_dir)
        
        # Запускаем в отдельном потоке
        threading.Thread(target=run_in_thread, daemon=True).start()
    
    def open_xlsm_file(self):
        """Обработчик для кнопки 6.1: Открытие .xlsm файла"""
        if not self.program_directory:
            messagebox.showwarning("Предупреждение", "Сначала выберите рабочий каталог программы")
            return
        
        if not self.selected_xlsx_file:
            messagebox.showwarning("Предупреждение", "Сначала выберите .xlsx файл (шаг 5)")
            return
        
        # Получаем имя файла без расширения
        xlsx_filename = os.path.basename(self.selected_xlsx_file)
        base_name = os.path.splitext(xlsx_filename)[0]
        
        # Формируем путь к .xlsm файлу в каталоге gear_xls/excel_exports
        xlsm_path = os.path.join(self.program_directory, "gear_xls", "excel_exports", f"{base_name}.xlsm")
        
        if not os.path.exists(xlsm_path):
            messagebox.showwarning("Предупреждение", 
                                  f"Файл .xlsm не найден: {xlsm_path}\n\nСначала конвертируйте .xlsx файл в .xlsm (кнопка 6)")
            return
        
        try:
            if platform.system() == "Windows":
                os.startfile(xlsm_path)
            elif platform.system() == "Darwin":  # macOS
                subprocess.Popen(["open", xlsm_path])
            else:  # Linux и др.
                subprocess.Popen(["xdg-open", xlsm_path])
            self.log_action(f"Открыт файл: {xlsm_path}")
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось открыть файл: {e}")

    def convert_to_xlsm(self):
        """Обработчик для кнопки 6: Конвертирование в .xlsm"""
        if not self.program_directory:
            messagebox.showwarning("Предупреждение", "Сначала выберите рабочий каталог программы")
            return
        
        if not self.selected_xlsx_file:
            messagebox.showwarning("Предупреждение", "Сначала выберите .xlsx файл (шаг 5)")
            return
        
        self.log_action("Конвертирование в .xlsm...")
        
        # Получаем имя файла и относительный путь к нему от каталога gear_xls
        xlsx_filename = os.path.basename(self.selected_xlsx_file)
        
        # Теперь команда использует относительный путь для файла,
        # так как файл уже находится в подкаталоге gear_xls/excel_exports
        commands = [f"python convert_to_xlsm.py excel_exports/{xlsx_filename}"]
        
        # Определяем функцию для выполнения в отдельном потоке
        def run_in_thread():
            self.terminal_process = self.execute_in_terminal(commands, os.path.join(self.program_directory, "gear_xls"))
        
        # Запускаем в отдельном потоке
        threading.Thread(target=run_in_thread, daemon=True).start()

    def run_scheduler_newpref(self):
        """Обработчик для кнопки 7: Запуск планировщика с newpref.xlsx"""
        if not self.program_directory:
            messagebox.showwarning("Предупреждение", "Сначала выберите рабочий каталог программы")
            return
        
        self.log_action("Запуск планировщика с newpref.xlsx...")
        
        # Команды для выполнения
        commands = [
            "python main_sch.py xlsx_initial/newpref.xlsx --time-limit 300 --verbose --time-interval 5"
        ]
        
        # Определяем функцию для выполнения в отдельном потоке
        def run_in_thread():
            self.terminal_process = self.execute_in_terminal(commands, self.program_directory)
        
        # Запускаем в отдельном потоке
        threading.Thread(target=run_in_thread, daemon=True).start()

    def open_pdf_visualization(self):
        """Обработчик для кнопки 4.1: Открытие PDF-визуализации"""
        if not self.program_directory:
            messagebox.showwarning("Предупреждение", "Сначала выберите рабочий каталог программы")
            return
        
        file_path = os.path.join(self.program_directory, "visualiser", "enhanced_schedule_visualization.pdf")
        
        if not os.path.exists(file_path):
            messagebox.showwarning("Предупреждение", 
                                  f"Файл не найден: {file_path}")
            return
        
        try:
            if platform.system() == "Windows":
                os.startfile(file_path)
            elif platform.system() == "Darwin":  # macOS
                subprocess.Popen(["open", file_path])
            else:  # Linux и др.
                subprocess.Popen(["xdg-open", file_path])
            self.log_action(f"Открыт файл: {file_path}")
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось открыть файл: {e}")

    def open_html_visualization(self):
        """Обработчик для кнопки 4.2: Открытие HTML-визуализации"""
        if not self.program_directory:
            messagebox.showwarning("Предупреждение", "Сначала выберите рабочий каталог программы")
            return
        
        file_path = os.path.join(self.program_directory, "visualiser", "enhanced_schedule_visualization.html")
        
        if not os.path.exists(file_path):
            messagebox.showwarning("Предупреждение", 
                                  f"Файл не найден: {file_path}")
            return
        
        try:
            webbrowser.open(f"file://{file_path}")
            self.log_action(f"Открыт файл: {file_path}")
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось открыть файл: {e}")


if __name__ == "__main__":
    # Создаем экземпляр Tk
    root = tk.Tk()
    
    # Применяем тему оформления
    style = ttk.Style()
    try:
        style.theme_use("clam")  # Более современная тема, если доступна
    except:
        pass  # Используем тему по умолчанию, если "clam" недоступна
    
    # Создаем приложение
    app = ApplicationInterface(root)
    
    # Запускаем основной цикл
    root.mainloop()