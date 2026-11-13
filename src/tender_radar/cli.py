import argparse


def main(argv=None):
    p = argparse.ArgumentParser(prog="tender-radar")
    p.add_subparsers(dest="cmd", required=True)
    p.parse_args(argv)


if __name__ == "__main__":
    main()
