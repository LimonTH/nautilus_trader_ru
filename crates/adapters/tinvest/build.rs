fn main() -> Result<(), Box<dyn std::error::Error>> {
    tonic_build::configure()
        .build_client(true)
        .build_server(false)
        .compile_protos(
            &[
                "proto/instruments.proto",
                "proto/marketdata.proto",
                "proto/operations.proto",
                "proto/orders.proto",
                "proto/users.proto",
                "proto/stoporders.proto",
                "proto/sandbox.proto",
                "proto/signals.proto",
                "proto/common.proto",
            ],
            &["proto", "proto/google/api"],
        )?;
    Ok(())
}
