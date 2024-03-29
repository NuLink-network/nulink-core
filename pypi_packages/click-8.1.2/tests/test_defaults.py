import nuclick as click


def test_basic_defaults(runner):
    @click.command()
    @click.option("--foo", default=42, type=click.FLOAT)
    def cli(foo):
        assert type(foo) is float
        click.echo(f"FOO:[{foo}]")

    result = runner.invoke(cli, [])
    assert not result.exception
    assert "FOO:[42.0]" in result.output


def test_multiple_defaults(runner):
    @click.command()
    @click.option("--foo", default=[23, 42], type=click.FLOAT, multiple=True)
    def cli(foo):
        for item in foo:
            assert type(item) is float
            click.echo(item)

    result = runner.invoke(cli, [])
    assert not result.exception
    assert result.output.splitlines() == ["23.0", "42.0"]


def test_nargs_plus_multiple(runner):
    @click.command()
    @click.option(
        "--arg", default=((1, 2), (3, 4)), nargs=2, multiple=True, type=click.INT
    )
    def cli(arg):
        for a, b in arg:
            click.echo(f"<{a:d}|{b:d}>")

    result = runner.invoke(cli, [])
    assert not result.exception
    assert result.output.splitlines() == ["<1|2>", "<3|4>"]
