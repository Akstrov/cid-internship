// src/app/components/viewer/viewer.component.ts
import { Component, OnInit, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Subject, debounceTime, distinctUntilChanged, takeUntil } from 'rxjs';
import { ApiService, PairSummary, PairDetail, StatusResponse } from '../../services/api.service';

@Component({
  selector: 'app-viewer',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './viewer.component.html',
  styleUrls: ['./viewer.component.css'],
})
export class ViewerComponent implements OnInit, OnDestroy {
  // Status bar
  status: StatusResponse | null = null;

  // Left panel — pair list
  pairs: PairSummary[] = [];
  totalPairs  = 0;
  currentPage = 1;
  totalPages  = 1;
  readonly limit = 20;

  // Search
  searchQuery = '';
  private search$ = new Subject<string>();

  // Right panel — selected pair
  selectedId  : string | null = null;
  detail      : PairDetail | null = null;
  imageUrl    : string | null = null;
  loadingDetail = false;

  private destroy$ = new Subject<void>();

  constructor(private api: ApiService) {}

  ngOnInit(): void {
    this.api.getStatus()
      .pipe(takeUntil(this.destroy$))
      .subscribe(s => this.status = s);

    this.loadPairs();

    // Debounce search input
    this.search$
      .pipe(debounceTime(300), distinctUntilChanged(), takeUntil(this.destroy$))
      .subscribe(q => {
        this.searchQuery = q;
        this.currentPage = 1;
        this.loadPairs();
      });
  }

  ngOnDestroy(): void {
    this.destroy$.next();
    this.destroy$.complete();
  }

  onSearchInput(value: string): void {
    this.search$.next(value);
  }

  loadPairs(): void {
    this.api.getPairs(this.currentPage, this.limit, this.searchQuery)
      .pipe(takeUntil(this.destroy$))
      .subscribe(res => {
        this.pairs      = res.items;
        this.totalPairs = res.total;
        this.totalPages = res.pages;
      });
  }

  selectPair(id: string): void {
    if (this.selectedId === id) return;
    this.selectedId   = id;
    this.detail       = null;
    this.imageUrl     = null;
    this.loadingDetail = true;

    this.api.getPair(id)
      .pipe(takeUntil(this.destroy$))
      .subscribe({
        next: d => {
          this.detail        = d;
          this.imageUrl      = this.api.getImageUrl(id);
          this.loadingDetail = false;
        },
        error: () => { this.loadingDetail = false; }
      });
  }

  prevPage(): void {
    if (this.currentPage > 1) {
      this.currentPage--;
      this.loadPairs();
    }
  }

  nextPage(): void {
    if (this.currentPage < this.totalPages) {
      this.currentPage++;
      this.loadPairs();
    }
  }

  // Helper: split a commentary section label from its content
  // e.g. "Causes probables : foo bar" → { label: "Causes probables", text: "foo bar" }
  splitLabel(text: string): { label: string; body: string } {
    const m = text.match(/^([^:]{3,40}?)\s*:\s*(.+)/s);
    if (m) return { label: m[1].trim(), body: m[2].trim() };
    return { label: '', body: text };
  }
}
