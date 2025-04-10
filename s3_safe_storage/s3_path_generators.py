def plain_name(file_name: str) -> str:
    return file_name

def generate_s3_file_name(file_struct: dto_bundle.FileStruct) -> str:
    hash_for_filename: typing.Final = hashlib.sha3_224
    rand_secret_bytes: typing.Final = secrets.token_bytes(256)
    current_month: typing.Final = datetime.datetime.now(tz=datetime.UTC).strftime("%m-%Y")
    filename_suffix: typing.Final = settings.known_mimes_to_extensions.get(file_struct.mime, "")

    if not file_struct.name:
        logger.warning("File name has not provided")
        rand_result_file_name: typing.Final = hash_for_filename(rand_secret_bytes).hexdigest()
        return f"{current_month}/{rand_result_file_name}.{filename_suffix}"

    encoded_file_name: typing.Final = file_struct.name.encode("utf-8", errors="ignore")
    result_file_name: typing.Final = hash_for_filename(rand_secret_bytes + encoded_file_name).hexdigest()
    return f"{current_month}/{result_file_name}.{filename_suffix}"
