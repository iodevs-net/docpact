// CONTRATO:
//   input:
//     props: object
//   output: JSX.Element
function MiComponente(props: { name: string }): JSX.Element {
    return <div>{props.name}</div>;
}