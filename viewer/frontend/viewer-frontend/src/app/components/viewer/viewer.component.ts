// src/app/components/viewer/viewer.component.ts
import { Component, OnInit, OnDestroy, ChangeDetectorRef } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Subject, debounceTime, distinctUntilChanged, takeUntil } from 'rxjs';
import { ApiService, PairSummary, PairDetail, StatusResponse } from '../../services/api.service';
import { UploadComponent } from '../upload/upload.component';

@Component({
  selector: 'app-viewer',
  standalone: true,
  imports: [FormsModule, UploadComponent],
  templateUrl: './viewer.component.html',
  styleUrls: ['./viewer.component.css'],
})
export class ViewerComponent implements OnInit, OnDestroy {
  // Tab
  activeTab: 'browse' | 'upload' = 'browse';

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
  selectedId : string | null = null;
  detail     : PairDetail | null = null;
  imageUrl   : string | null = null;
  loading    = false;

  private destroy$ = new Subject<void>();

  constructor(private api: ApiService, private cdr: ChangeDetectorRef) {}

  ngOnInit(): void {
    this.api.getStatus()
      .pipe(takeUntil(this.destroy$))
      .subscribe(s => { this.status = s; this.cdr.detectChanges(); });

    this.loadPairs();

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

  onSearchInput(value: string): void { this.search$.next(value); }

  loadPairs(): void {
    this.api.getPairs(this.currentPage, this.limit, this.searchQuery)
      .pipe(takeUntil(this.destroy$))
      .subscribe(res => {
        this.pairs      = res.items;
        this.totalPairs = res.total;
        this.totalPages = res.pages;
        this.cdr.detectChanges();
      });
  }

  selectPair(id: string): void {
    if (this.selectedId === id) return;
    this.selectedId = id;
    this.detail     = null;
    this.imageUrl   = null;
    this.loading    = true;
    this.cdr.detectChanges();

    this.api.getPair(id)
      .pipe(takeUntil(this.destroy$))
      .subscribe({
        next: d => {
          this.detail   = d;
          this.imageUrl = this.api.getImageUrl(id);
          this.loading  = false;
          this.cdr.detectChanges();
        },
        error: () => { this.loading = false; this.cdr.detectChanges(); }
      });
  }

  onUploadSuccess(newId: string): void {
    // Switch to browse, reload list, then auto-select the new record
    this.activeTab   = 'browse';
    this.currentPage = 1;
    this.api.getStatus()
      .pipe(takeUntil(this.destroy$))
      .subscribe(s => { this.status = s; this.cdr.detectChanges(); });
    this.api.getPairs(1, this.limit, '')
      .pipe(takeUntil(this.destroy$))
      .subscribe(res => {
        this.pairs      = res.items;
        this.totalPairs = res.total;
        this.totalPages = res.pages;
        this.cdr.detectChanges();
        // Auto-select the newly uploaded pair
        if (newId) this.selectPair(newId);
      });
  }

  prevPage(): void {
    if (this.currentPage > 1) { this.currentPage--; this.loadPairs(); }
  }

  nextPage(): void {
    if (this.currentPage < this.totalPages) { this.currentPage++; this.loadPairs(); }
  }
}
