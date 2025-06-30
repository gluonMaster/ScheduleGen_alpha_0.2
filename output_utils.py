"""
Module for output utilities.
"""

import pandas as pd

def get_schedule_dataframe(optimizer):
    """
    Get the schedule as a pandas DataFrame.
    
    Returns:
        DataFrame with the schedule or None if no solution exists
    """
    if not optimizer.solution:
        return None
        
    return pd.DataFrame(optimizer.solution)

def get_teacher_schedule(optimizer, teacher):
    """
    Get the schedule for a specific teacher.
    
    Args:
        teacher: Name of the teacher
        
    Returns:
        DataFrame with the teacher's schedule or None if no solution exists
    """
    if not optimizer.solution:
        return None
        
    df = pd.DataFrame(optimizer.solution)
    return df[df["teacher"] == teacher].sort_values(by=["day", "start_time"])

def get_group_schedule(optimizer, group):
    """
    Get the schedule for a specific group.
    
    Args:
        group: Name of the group
        
    Returns:
        DataFrame with the group's schedule or None if no solution exists
    """
    if not optimizer.solution:
        return None
        
    df = pd.DataFrame(optimizer.solution)
    # Filter for classes that have this group
    return df[df["group"].str.contains(group, na=False)].sort_values(by=["day", "start_time"])

def get_room_schedule(optimizer, room):
    """
    Get the schedule for a specific room.
    
    Args:
        room: Name of the room
        
    Returns:
        DataFrame with the room's schedule or None if no solution exists
    """
    if not optimizer.solution:
        return None
        
    df = pd.DataFrame(optimizer.solution)
    return df[df["room"] == room].sort_values(by=["day", "start_time"])

def export_to_excel(optimizer, filename="schedule.xlsx"):
    """
    Export the schedule to an Excel file.
    
    Args:
        filename: Path to the output Excel file
        
    Returns:
        True if export was successful, False otherwise
    """
    if not optimizer.solution:
        return False
    
    # Используем контекстный менеджер для автоматического закрытия файла
    with pd.ExcelWriter(filename, engine='openpyxl') as writer:
        # Main schedule
        main_df = pd.DataFrame(optimizer.solution)
        main_df.to_excel(writer, sheet_name="Schedule", index=False)
        
        # Teacher schedules
        for teacher in optimizer.teachers:
            teacher_df = get_teacher_schedule(optimizer, teacher)
            if teacher_df is not None and not teacher_df.empty:
                # Create a safe sheet name (max 31 chars)
                sheet_name = f"T_{teacher}"[:31]
                teacher_df.to_excel(writer, sheet_name=sheet_name, index=False)
        
        # Group schedules
        for group in optimizer.groups:
            group_df = get_group_schedule(optimizer, group)
            if group_df is not None and not group_df.empty:
                # Create a safe sheet name (max 31 chars)
                sheet_name = f"G_{group}"[:31]
                group_df.to_excel(writer, sheet_name=sheet_name, index=False)
        
        # Room schedules
        for room in optimizer.rooms:
            room_df = get_room_schedule(optimizer, room)
            if room_df is not None and not room_df.empty:
                # Create a safe sheet name (max 31 chars)
                sheet_name = f"R_{room}"[:31]
                room_df.to_excel(writer, sheet_name=sheet_name, index=False)
    
    # Файл уже закрыт благодаря контекстному менеджеру
    return True