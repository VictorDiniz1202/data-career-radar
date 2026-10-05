import argparse

def main():
    parser = argparse.ArgumentParser(description="Data Career Radar CLI")
    parser.add_argument("--action", choices=["ingest", "normalize"], help="Action to perform")
    
    args = parser.parse_args()
    
    if args.action == "ingest":
        print("Ingestion not implemented yet.")
    elif args.action == "normalize":
        print("Normalization not implemented yet.")
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
