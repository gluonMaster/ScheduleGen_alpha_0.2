import pandas as pd

# Читаем результат оптимизации
df = pd.read_excel('optimized_schedule.xlsx', sheet_name='Schedule')

print('=== РЕЗУЛЬТАТ ОПТИМИЗАЦИИ ===')
for i, row in df.iterrows():
    print(f"{row['subject']} {row['group']} {row['teacher']} {row['room']} {row['day']} {row['start_time']}-{row['end_time']}")

print('\n=== КОНФЛИКТЫ АУДИТОРИЙ ===')
for room in df['room'].unique():
    room_schedule = df[df['room'] == room].sort_values('start_time')
    if len(room_schedule) > 1:
        print(f'\nАудитория {room}:')
        for i, row in room_schedule.iterrows():
            print(f"  {row['start_time']}-{row['end_time']}: {row['subject']} {row['group']} {row['teacher']}")
