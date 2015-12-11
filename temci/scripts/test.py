import click, sys

@click.command()
@click.argument("run_file")
@click.option("abc")
@click.option("abc", "a")
def cli(run_file: str, *list):
    print(run_file)
    print(list)
    @click.group()
    def base_func():
        pass
    if run_file.endswith(".exec.yaml"):
        @base_func.command(run_file)
        def func():
            print("exec")

    base_func()


sys.argv[1:] = ["abc.exe.yaml"]

cli()