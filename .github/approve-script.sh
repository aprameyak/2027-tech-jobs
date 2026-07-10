#!/bin/bash
# Approve clearly in-scope tech roles

ISSUES=(525 524 523 522 521 520 519 518 517 516 515 514 513 512 509 508 507 506 505 502 501 500 499 492 491 489 488 487 486 478 477 476 475 474 473 464 463 462 461 460 459 458 457 456 455 454 453 452 451 450 449 448 447 439 409 408 407)

for ISSUE in "${ISSUES[@]}"; do
  curl -X POST \
    -H "Authorization: token $GITHUB_TOKEN" \
    -H "Accept: application/vnd.github.v3+json" \
    https://api.github.com/repos/aprameyak/2027-tech-jobs/issues/$ISSUE/labels \
    -d '{"labels":["approved"]}'
  echo "Approved issue #$ISSUE"
done
