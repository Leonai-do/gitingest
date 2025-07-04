"""Main entry point for ingesting a source and processing its contents."""

import asyncio
import inspect
import shutil
from pathlib import Path
from typing import Optional, Set, Tuple, Union

from gitingest.cloning import clone_repo
from gitingest.streaming import stream_remote_repo
from gitingest.config import TMP_BASE_PATH
from gitingest.ingestion import ingest_query
from gitingest.query_parsing import IngestionQuery, parse_query


async def ingest_async(
    source: str,
    max_file_size: int = 10 * 1024 * 1024,  # 10 MB
    include_patterns: Optional[Union[str, Set[str]]] = None,
    exclude_patterns: Optional[Union[str, Set[str]]] = None,
    branch: Optional[str] = None,
    output: Optional[str] = None,
    parallel: bool = False,
    incremental: bool = False,
    compress: bool = False,
    stream: bool = False,
    output_format: str = "text",
) -> Tuple[str, str, str]:
    # pylint: disable=unused-argument
    """
    Main entry point for ingesting a source and processing its contents.

    This function analyzes a source (URL or local path), clones the corresponding repository (if applicable),
    and processes its files according to the specified query parameters. It returns a summary, a tree-like
    structure of the files, and the content of the files. The results can optionally be written to an output file.

    Parameters
    ----------
    source : str
        The source to analyze, which can be a URL (for a Git repository) or a local directory path.
    max_file_size : int
        Maximum allowed file size for file ingestion. Files larger than this size are ignored, by default
        10*1024*1024 (10 MB).
    include_patterns : Union[str, Set[str]], optional
        Pattern or set of patterns specifying which files to include. If `None`, all files are included.
    exclude_patterns : Union[str, Set[str]], optional
        Pattern or set of patterns specifying which files to exclude. If `None`, no files are excluded.
    branch : str, optional
        The branch to clone and ingest. If `None`, the default branch is used.
    output : str, optional
        File path where the summary and content should be written. If `None`, the results are not written to a file.
    parallel : bool
        Enable multithreaded scanning.
    incremental : bool
        Use on-disk cache to skip unchanged files.
    compress : bool
        Write gzip compressed output.
    stream : bool
        Download repository using the GitHub API instead of git clone.
    parallel : bool
        Enable multithreaded scanning.
    incremental : bool
        Use on-disk cache to skip unchanged files.
    compress : bool
        Write gzip compressed output.

    Returns
    -------
    Tuple[str, str, str]
        A tuple containing:
        - A summary string of the analyzed repository or directory.
        - A tree-like string representation of the file structure.
        - The content of the files in the repository or directory.

    Raises
    ------
    TypeError
        If `clone_repo` does not return a coroutine, or if the `source` is of an unsupported type.
    """
    repo_cloned = False

    try:
        query: IngestionQuery = await parse_query(
            source=source,
            max_file_size=max_file_size,
            from_web=False,
            include_patterns=include_patterns,
            ignore_patterns=exclude_patterns,
        )
        query.output_format = output_format

        if query.url:
            selected_branch = branch if branch else query.branch
            query.branch = selected_branch

            if stream:
                await asyncio.to_thread(
                    stream_remote_repo,
                    query.url,
                    branch=selected_branch,
                    subpath=query.subpath,
                    dest=query.local_path,
                )
            else:
                clone_config = query.extract_clone_config()
                clone_coroutine = clone_repo(clone_config)

                if inspect.iscoroutine(clone_coroutine):
                    if asyncio.get_event_loop().is_running():
                        await clone_coroutine
                    else:
                        asyncio.run(clone_coroutine)
                else:
                    raise TypeError("clone_repo did not return a coroutine as expected.")

            repo_cloned = True

        summary, tree, content = ingest_query(query, output_format=output_format)

        if output is not None:
            from gitingest.output_utils import write_digest  # pylint: disable=C0415

            write_digest(tree + "\n" + content, Path(output), compress)

        return summary, tree, content
    finally:
        # Clean up the temporary directory if it was created
        if repo_cloned:
            shutil.rmtree(TMP_BASE_PATH, ignore_errors=True)


def ingest(
    source: str,
    max_file_size: int = 10 * 1024 * 1024,  # 10 MB
    include_patterns: Optional[Union[str, Set[str]]] = None,
    exclude_patterns: Optional[Union[str, Set[str]]] = None,
    branch: Optional[str] = None,
    output: Optional[str] = None,
    parallel: bool = False,
    incremental: bool = False,
    compress: bool = False,
    stream: bool = False,
    output_format: str = "text",
) -> Tuple[str, str, str]:
    """
    Synchronous version of ingest_async.

    This function analyzes a source (URL or local path), clones the corresponding repository (if applicable),
    and processes its files according to the specified query parameters. It returns a summary, a tree-like
    structure of the files, and the content of the files. The results can optionally be written to an output file.

    Parameters
    ----------
    source : str
        The source to analyze, which can be a URL (for a Git repository) or a local directory path.
    max_file_size : int
        Maximum allowed file size for file ingestion. Files larger than this size are ignored, by default
        10*1024*1024 (10 MB).
    include_patterns : Union[str, Set[str]], optional
        Pattern or set of patterns specifying which files to include. If `None`, all files are included.
    exclude_patterns : Union[str, Set[str]], optional
        Pattern or set of patterns specifying which files to exclude. If `None`, no files are excluded.
    branch : str, optional
        The branch to clone and ingest. If `None`, the default branch is used.
    output : str, optional
        File path where the summary and content should be written. If `None`, the results are not written to a file.

    Returns
    -------
    Tuple[str, str, str]
        A tuple containing:
        - A summary string of the analyzed repository or directory.
        - A tree-like string representation of the file structure.
        - The content of the files in the repository or directory.

    See Also
    --------
    ingest_async : The asynchronous version of this function.
    """
    return asyncio.run(
        ingest_async(
            source=source,
            max_file_size=max_file_size,
            include_patterns=include_patterns,
            exclude_patterns=exclude_patterns,
            branch=branch,
            output=output,
            parallel=parallel,
            incremental=incremental,
            compress=compress,
            stream=stream,
            output_format=output_format,
        )
    )
