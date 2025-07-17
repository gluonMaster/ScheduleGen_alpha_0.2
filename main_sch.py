import argparse
import os
import sys
import time
from datetime import datetime
from timewindow_adapter import apply_timewindow_improvements, add_objective_weights_for_timewindows

# Импорт модулей нашего приложения
from reader import ScheduleReader
from scheduler_base import ScheduleOptimizer
from output_utils import get_schedule_dataframe, export_to_excel, get_teacher_schedule
from constraint_registry import export_constraint_registry, print_infeasible_summary

default_output_path = "optimized_schedule.xlsx"

def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description='Generate optimized school schedule using OR-Tools.')
    
    parser.add_argument('input_file', help='Path to the Excel file with schedule planning data')
    parser.add_argument('--output', default=default_output_path,
                    help='Path to the output Excel file (default: optimized_schedule.xlsx)')
    parser.add_argument('--time-limit', type=int, default=300, 
                    help='Time limit for optimization in seconds (default: 300)')
    parser.add_argument('--time-interval', type=int, default=15, 
                    help='Time interval for scheduling in minutes (default: 15)')
    parser.add_argument('--verbose', action='store_true',
                    help='Enable verbose output')
    
    return parser.parse_args()


def print_summary(reader, classes):
    """Print a summary of the input data."""
    print(f"\n=== Input Data Summary ===")
    print(f"Total number of classes: {len(classes)}")
    print(f"Teachers: {len(reader.teachers)}")
    print(f"Groups: {len(reader.groups)}")
    print(f"Rooms: {len(reader.rooms)}")
    print(f"Buildings: {len(reader.buildings)}")
    print(f"Days: {sorted(reader.days)}")
    
    # Count classes by day
    days_count = {}
    for c in classes:
        if c.day:
            days_count[c.day] = days_count.get(c.day, 0) + 1
    
    print("\nClasses by day:")
    for day in sorted(days_count.keys()):
        print(f"  {day}: {days_count[day]} classes")
    
    # Count linked class chains
    linked_chains = 0
    linked_classes = 0
    for c in classes:
        if hasattr(c, 'linked_classes') and c.linked_classes:
            linked_chains += 1
            linked_classes += len(c.linked_classes)
    
    print(f"\nLinked class chains: {linked_chains}")
    print(f"Classes in linked chains: {linked_classes + linked_chains}")
    
    # Count classes with fixed times/rooms/time windows
    fixed_time = sum(1 for c in classes if c.start_time and not c.end_time)
    time_window = sum(1 for c in classes if c.start_time and c.end_time)
    any_time = sum(1 for c in classes if not c.start_time)
    fixed_room = sum(1 for c in classes if len(c.possible_rooms) == 1)
    
    print(f"\nClasses with fixed start times: {fixed_time} ({fixed_time/len(classes)*100:.1f}%)")
    print(f"Classes with time windows: {time_window} ({time_window/len(classes)*100:.1f}%)")
    print(f"Classes with any start time: {any_time} ({any_time/len(classes)*100:.1f}%)")
    print(f"Classes with fixed rooms: {fixed_room} ({fixed_room/len(classes)*100:.1f}%)")


def print_solution_summary(optimizer):
    """Print a summary of the optimization solution."""
    if not optimizer.solution:
        print("\n=== No Solution Found ===")
        return
        
    schedule_df = get_schedule_dataframe(optimizer)
    
    print(f"\n=== Solution Summary ===")
    print(f"Total scheduled classes: {len(schedule_df)}")
    
    # Classes by day
    day_counts = schedule_df["day"].value_counts().to_dict()
    print("\nScheduled classes by day:")
    for day in sorted(day_counts.keys()):
        print(f"  {day}: {day_counts[day]} classes")
    
    # Teacher load
    teacher_counts = schedule_df["teacher"].value_counts().to_dict()
    print("\nTeacher load (top 5):")
    for teacher, count in sorted(teacher_counts.items(), key=lambda x: x[1], reverse=True)[:5]:
        print(f"  {teacher}: {count} classes")
    
    # Room utilization
    room_counts = schedule_df["room"].value_counts().to_dict()
    print("\nRoom utilization (top 5):")
    for room, count in sorted(room_counts.items(), key=lambda x: x[1], reverse=True)[:5]:
        print(f"  {room}: {count} classes")
    
    # Time distribution
    schedule_df["hour"] = schedule_df["start_time"].str.split(":").str[0].astype(int)
    hour_counts = schedule_df["hour"].value_counts().to_dict()
    print("\nClass start time distribution:")
    for hour in sorted(hour_counts.keys()):
        print(f"  {hour}:00 - {hour+1}:00: {hour_counts[hour]} classes")


def main():
    """Main function to generate the optimized schedule."""
    # Parse command line arguments
    args = parse_arguments()
    
    # Validate input file
    if not os.path.exists(args.input_file):
        print(f"Error: Input file '{args.input_file}' does not exist.")
        sys.exit(1)
    
    # Create output directory if needed
    output_dir = os.path.dirname(args.output)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    print(f"Reading schedule data from '{args.input_file}'...")
    
    # Read the Excel file
    try:
        reader = ScheduleReader(args.input_file)
        classes = reader.read_excel()
    except Exception as e:
        print(f"Error reading Excel file: {str(e)}")
        sys.exit(1)
    
    if args.verbose:
        print_summary(reader, classes)

    print(f"\nCreating schedule optimization model...")
    optimizer = ScheduleOptimizer(classes, time_interval=args.time_interval)
    
    print(f"Solving schedule optimization problem (time limit: {args.time_limit} seconds)...")
    start_time = time.time()
    
    # Solve the model
    solution_found = optimizer.solve(time_limit_seconds=args.time_limit)
    
    end_time = time.time()
    elapsed_time = end_time - start_time
    
    if solution_found:
        print(f"\nSolution found in {elapsed_time:.2f} seconds!")
        
        if args.verbose:
            print_solution_summary(optimizer)
        
        # Export the result
        print(f"\nExporting schedule to '{args.output}'...")
        export_to_excel(optimizer, filename=args.output)
        print("Export completed successfully.")
        
        # Export constraint registry for analysis
        export_constraint_registry(optimizer.constraint_registry, optimizer, only_conflicts=False)
        
        print(f"\nSchedule generation complete.")
        print(f"Generated schedule saved to: {os.path.abspath(args.output)}")
        
        return 0
    else:
        print(f"\nNo solution found within the time limit ({elapsed_time:.2f} seconds).")
        
        # Check if the problem is INFEASIBLE
        if hasattr(optimizer, 'solver_status') and optimizer.solver_status == 'INFEASIBLE':
            print("\n❌ PROBLEM IS INFEASIBLE - No valid solution exists with current constraints.")
            
            # Отчеты уже сгенерированы в solver
            print("\n💡 Possible solutions:")
            print("  1. Relax some time constraints")
            print("  2. Add more rooms or increase room capacity")
            print("  3. Adjust teacher availability")
            print("  4. Reduce required classes or increase time slots")
            print("  5. Review constraint_registry_infeasible.txt for detailed analysis")
            
        else:
            print("The solver timed out. Try increasing the time limit or relaxing some constraints.")
            
            # Export constraint registry for analysis even on timeout
            export_constraint_registry(optimizer.constraint_registry, optimizer, only_conflicts=False)
        
        return 1


if __name__ == "__main__":
    sys.exit(main())